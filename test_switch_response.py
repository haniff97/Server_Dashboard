"""Exercise the command flow without hardware or controller startup imports."""
import ast
import asyncio
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def load_command_flow(io_bound, insert):
    source = ast.parse((Path(__file__).parent / 'controllers/plug_controller.py').read_text())
    names = {'_state_log_tasks', '_log_switch_change', 'toggle_plug'}
    nodes = [node for node in source.body if getattr(node, 'name', None) in names
             or isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) in names]
    switch = Mock(return_value=True)
    state = SimpleNamespace(plug_lock=threading.Lock(), plug_state={'plug': {'status': {'switch': False}}})
    namespace = dict(asyncio=asyncio, run=SimpleNamespace(io_bound=io_bound), state=state,
                     tuya_local=SimpleNamespace(set_switch=switch, DEVICES={'plug': {'id': 'test', 'name': 'Test'}}),
                     db=SimpleNamespace(insert_state_change=insert))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<command-flow>', 'exec'), namespace)
    return namespace, switch, state


class SwitchResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_database_does_not_hold_response(self):
        started, release = asyncio.Event(), asyncio.Event()
        insert = Mock()
        async def io_bound(fn, *args):
            if fn is insert:
                started.set()
                await release.wait()
            return fn(*args)
        ns, switch, state = load_command_flow(io_bound, insert)
        self.assertTrue(await asyncio.wait_for(ns['toggle_plug']('plug', True), .5))
        self.assertTrue(state.plug_state['plug']['status']['switch'])
        await started.wait()
        insert.assert_not_called()
        release.set()
        await asyncio.gather(*ns['_state_log_tasks'])
        insert.assert_called_once_with('test', 'Test', True)

    async def test_failed_command_does_not_log_or_change_state(self):
        async def io_bound(fn, *args): return fn(*args)
        insert = Mock()
        ns, switch, state = load_command_flow(io_bound, insert)
        switch.return_value = False
        self.assertFalse(await ns['toggle_plug']('plug', True))
        self.assertFalse(state.plug_state['plug']['status']['switch'])
        self.assertFalse(ns['_state_log_tasks'])
        insert.assert_not_called()

    async def test_log_failure_does_not_change_success(self):
        async def io_bound(fn, *args): return fn(*args)
        insert = Mock(side_effect=RuntimeError('Database unavailable'))
        ns, switch, state = load_command_flow(io_bound, insert)
        self.assertTrue(await ns['toggle_plug']('plug', True))
        await asyncio.gather(*ns['_state_log_tasks'])
        self.assertTrue(state.plug_state['plug']['status']['switch'])

if __name__ == '__main__': unittest.main()
