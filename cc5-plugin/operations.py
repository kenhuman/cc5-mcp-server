"""Bounded, session-local operation journal. No CC5/Qt dependencies."""
import json
import threading
import time
import uuid
from collections import OrderedDict


class Operations:
    def __init__(self, capacity=1000):
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.capacity = capacity
        self.session = uuid.uuid4().hex
        self.heartbeat = None
        self.modal_dialog_open = False

    def submit(self, action, params, operation_id=None):
        identity = json.dumps([action, params], sort_keys=True)
        with self.lock:
            key = operation_id or uuid.uuid4().hex
            if key in self.jobs:
                job = self.jobs[key]
                if job['identity'] != identity:
                    raise ValueError('Operation ID already used for different arguments')
                return job, False
            # Never evict IDs: an old retry must not silently execute again.
            if len(self.jobs) >= self.capacity:
                raise RuntimeError('Operation journal full; restart only after reviewing completed work')
            job = dict(id=key, action=action, params=params, identity=identity,
                       state='queued', event=threading.Event(), result=None)
            self.jobs[key] = job
            return job, True

    def start(self, job):
        with self.lock:
            if job['state'] != 'queued':
                return False
            job['state'] = 'running'
            return True

    def finish(self, job, result):
        with self.lock:
            job['result'] = result
            job['state'] = 'failed' if isinstance(result, dict) and result.get('success') is False else 'completed'
            job['event'].set()

    def expire(self, job):
        with self.lock:
            if job['state'] == 'queued':
                job['state'] = 'cancelled'
                job['event'].set()
            elif job['state'] == 'running':
                job['state'] = 'outcome_unknown'
            return self.snapshot(job['id'])

    def snapshot(self, key):
        with self.lock:
            job = self.jobs.get(key)
            if job is None:
                return None
            return {k: job[k] for k in ('id', 'action', 'state', 'result')}

    def status(self):
        with self.lock:
            age = None if self.heartbeat is None else time.monotonic() - self.heartbeat
            return dict(session_id=self.session, main_thread_age_seconds=age,
                        main_thread_responsive=age is not None and age < 2,
                        modal_dialog_open=self.modal_dialog_open,
                        active_operations=[self.snapshot(k) for k, v in self.jobs.items()
                                           if v['state'] in ('running', 'outcome_unknown')],
                        journal_used=len(self.jobs), journal_capacity=self.capacity)
