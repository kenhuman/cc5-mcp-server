"""Offline tests: stub native module, never connect to or launch CC5."""
import importlib.util
import json
import queue
import sys
import threading
import time
import types
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cc5-plugin'))
sys.modules['cc5_api'] = types.ModuleType('cc5_api')
import server
from operations import Operations


class QueueTests(unittest.TestCase):
    def setUp(self):
        server.operations = Operations()
        server.command_queue = queue.Queue(maxsize=100)
        server.READ_ONLY = False
        server.PAUSE_FILE = ''
        self.calls = []
        server.ACTION_MAP['probe'] = lambda p: self.calls.append(p) or {'success': True}

    def test_timeout_cancels_queued_mutation(self):
        status, body = server._execute_sync('probe', {}, timeout=.001, operation_id='one')
        self.assertEqual(status, 504)
        self.assertEqual(body['operation']['state'], 'cancelled')
        server.process_command_queue()
        self.assertEqual(self.calls, [])
        self.assertEqual(server._execute_sync('probe', {}, operation_id='one')[0], 409)

    def test_only_headshot_commands_run_inside_its_modal(self):
        server.operations.modal_dialog_open = True
        blocked,_ = server.operations.submit('probe', {}, 'blocked')
        allowed,_ = server.operations.submit('headshot_state', {}, 'allowed')
        server.command_queue.put(blocked)
        server.command_queue.put(allowed)
        with patch.object(server.headshot,'owns_modal',return_value=True), patch.dict(server.ACTION_MAP,{'headshot_state':lambda p:{'success':True}}):
            server.process_command_queue()
            self.assertEqual(blocked['state'],'queued')
            server.process_command_queue()
            self.assertEqual(allowed['state'],'completed')
            self.assertEqual(self.calls,[])

    def test_headshot_does_not_run_inside_unrelated_modal(self):
        server.operations.modal_dialog_open = True
        job,_ = server.operations.submit('headshot_generate', {'prepared_id':'x'}, 'modal')
        server.command_queue.put(job)
        with patch.object(server.headshot,'owns_modal',return_value=False):
            server.process_command_queue()
        self.assertEqual(job['state'],'queued')

    def test_refinement_modal_only_dispatches_fitting_actions(self):
        server.operations.modal_dialog_open=True
        blocked,_=server.operations.submit('headshot_generate',{'prepared_id':'x'},'refine-blocked')
        allowed,_=server.operations.submit('fitting_state',{},'refine-read')
        server.command_queue.put(blocked);server.command_queue.put(allowed)
        with patch.object(server.headshot,'owns_modal',return_value=False),patch.object(server.fitting,'owns_modal',return_value=True),patch.dict(server.ACTION_MAP,{'fitting_state':lambda p:{'success':True}}):
            server.process_command_queue();server.process_command_queue()
        self.assertEqual(blocked['state'],'queued');self.assertEqual(allowed['state'],'completed')

    def test_success_and_duplicate_execute_once(self):
        result = []
        worker = threading.Thread(target=lambda: result.append(server._execute_sync('probe', {}, operation_id='two')))
        worker.start()
        for _ in range(100):
            if not server.command_queue.empty():
                break
            time.sleep(.001)
        server.process_command_queue()
        worker.join(1)
        self.assertEqual(result[0][0], 200)
        self.assertEqual(server._execute_sync('probe', {}, operation_id='two')[0], 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(server._execute_sync('probe', {'different': True}, operation_id='two')[0], 409)

    def test_running_timeout_retains_outcome_and_blocks_new_mutations(self):
        job, _ = server.operations.submit('probe', {}, 'running')
        server.operations.start(job)
        state = server.operations.expire(job)
        self.assertEqual(state['state'], 'outcome_unknown')
        self.assertEqual(server._execute_sync('probe', {}, operation_id='new')[0], 409)
        server.operations.finish(job, {'success': True})
        self.assertEqual(server.operations.snapshot('running')['state'], 'completed')

    def test_pause_rechecked_before_dispatch(self):
        job, _ = server.operations.submit('probe', {}, 'pause')
        server.command_queue.put(job)
        server.PAUSE_FILE = __file__
        server.process_command_queue()
        self.assertEqual(self.calls, [])
        self.assertEqual(job['state'], 'failed')

    def test_read_only_blocks_unknown_actions(self):
        server.READ_ONLY = True
        self.assertEqual(server._execute_sync('probe', {})[0], 403)
        self.assertEqual(server.command_queue.qsize(), 0)

    def test_journal_never_evicts_deduplication_ids(self):
        journal = Operations(capacity=1)
        job, _ = journal.submit('probe', {}, 'one')
        journal.expire(job)
        with self.assertRaises(RuntimeError):
            journal.submit('probe', {}, 'two')
        self.assertFalse(journal.submit('probe', {}, 'one')[1])

    def test_heartbeat_distinguishes_never_serviced(self):
        self.assertFalse(server.operations.status()['main_thread_responsive'])
        server.process_command_queue()
        self.assertTrue(server.operations.status()['main_thread_responsive'])
        server.operations.heartbeat = time.monotonic() - 5
        self.assertFalse(server.operations.status()['main_thread_responsive'])

    def test_no_new_execution_after_cancel_race(self):
        for _ in range(100):
            job, _ = server.operations.submit('probe', {})
            server.operations.expire(job)
            self.assertFalse(server.operations.start(job))

    def test_experimental_export_blocked(self):
        with patch.dict('os.environ', {'CC5_ALLOW_EXPERIMENTAL': '0'}):
            self.assertEqual(server._execute_sync('export_fbx', {'output_path': 'test.fbx'})[0], 403)

    def test_modal_dialog_defers_work_until_timeout_cancels_it(self):
        job, _ = server.operations.submit('probe', {}, 'modal')
        server.command_queue.put(job)
        server.operations.modal_dialog_open = True
        server.process_command_queue()
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(self.calls, [])
        server.operations.expire(job)
        server.operations.modal_dialog_open = False
        server.process_command_queue()
        self.assertEqual(self.calls, [])

    def test_worker_exception_is_retained(self):
        def fail(params):
            raise RuntimeError('native wrapper error')
        server.ACTION_MAP['probe'] = fail
        job, _ = server.operations.submit('probe', {}, 'failure')
        server.command_queue.put(job)
        server.process_command_queue()
        self.assertEqual(job['state'], 'failed')
        self.assertIn('native wrapper error', job['result']['error'])


class HttpTests(unittest.TestCase):
    def setUp(self):
        server.operations = Operations()
        server.BRIDGE_TOKEN = 'test-only-token-with-at-least-32-characters'
        self.httpd = server.ReusableHTTPServer(('127.0.0.1', 0), server.BridgeHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def request(self, path, token=True, origin=None):
        headers = {'Authorization': 'Bearer ' + server.BRIDGE_TOKEN} if token else {}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (self.httpd.server_port, path), headers=headers)
        return urllib.request.urlopen(req, timeout=2)

    def test_authentication_and_browser_rejection(self):
        for token, origin, expected in [(False, None, 401), (True, 'https://example.com', 403)]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/health', token, origin)
            self.assertEqual(error.exception.code, expected)

    def test_status_without_main_thread_and_disabled_reload(self):
        with self.request('/health') as response:
            data = json.load(response)['result']
        self.assertFalse(data['main_thread_responsive'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/reload')
        self.assertEqual(error.exception.code, 403)
        with self.request('/capabilities') as response:
            self.assertIn('qualification', json.load(response)['result'])


if __name__ == '__main__':
    unittest.main()
