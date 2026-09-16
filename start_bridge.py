"""Load once through CC5's Python script loader; restart CC5 to update code."""
import builtins
import os
import sys

if getattr(builtins, '_cc5_mcp_manual_bridge', None) is not None:
    raise RuntimeError('Bridge already loaded. Restart CC5 to update Python modules.')
if 'server' in sys.modules or 'main' in sys.modules:
    raise RuntimeError('A bridge or conflicting module is already loaded; use a fresh CC5 session.')
plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cc5-plugin')
sys.path.insert(0, plugin_dir)
import main as bridge_plugin
import RLPy
status = bridge_plugin.initialize_plugin()
if status != RLPy.RStatus.Success:
    raise RuntimeError('Bridge initialization failed; inspect the CC5 log and environment.')
builtins._cc5_mcp_manual_bridge = bridge_plugin
