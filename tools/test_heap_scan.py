"""Generated recovery controls for complete and interrupted heap scans."""
import contextlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import make_fixtures as F
import qq_keyfind as K


@contextlib.contextmanager
def heap_messages(events):
    script = Mock()
    session = Mock()
    session.create_script.return_value = script
    callback = {}

    def register(name, handler):
        if name != 'message':
            raise AssertionError(name)
        callback['message'] = handler

    def load():
        for event in events:
            callback['message']({'type': 'send', 'payload': event}, None)

    script.on.side_effect = register
    script.load.side_effect = load
    device = Mock()
    device.attach.return_value = session
    manager = Mock()
    manager.add_remote_device.return_value = device
    frida = types.SimpleNamespace(__version__='16.0.0', get_device_manager=lambda: manager)
    with patch.dict(sys.modules, {'frida': frida}):
        try:
            yield session
        finally:
            session.create_script.assert_called_once_with(K.JS)
            session.detach.assert_called_once_with()


class HeapScanTests(unittest.TestCase):
    def test_complete_generated_scan_recovers_verified_key(self):
        for name in ('healthy', 'deferred_healthy'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='qq-heap-fixture-') as directory:
                database = Path(directory)/'synthetic.db'
                F.build(str(database))
                with heap_messages(F.heap_scan_scenarios()[name]['events']):
                    bundle = K.recover_key(database, F.OWNER, seconds=1)
                self.assertEqual(bundle['key_hex'], F.SYNTH_KEY.hex())
                self.assertEqual(bundle['observation_source'], 'running_client_heap')
                expected = {seq: text for seq, text in F.known_pairs().items()
                            if len(text.encode('utf-8')) >= 2 * len(F.SYNTH_KEY)}
                self.assertEqual({row['uniseq']: row['plaintext'] for row in bundle['known_pairs']}, expected)

    def test_failed_generated_scan_refuses_even_with_enough_valid_pairs(self):
        for name, case in F.heap_scan_scenarios().items():
            if case['should_recover']:
                continue
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='qq-heap-fixture-') as directory:
                database = Path(directory)/'synthetic.db'
                F.build(str(database))
                with heap_messages(case['events']), self.assertRaisesRegex(RuntimeError, 'heap scan unavailable'):
                    K.recover_key(database, F.OWNER, seconds=1)

    def test_fatal_scan_outcome_takes_precedence_over_completion(self):
        cases = F.heap_scan_scenarios()
        for events in (cases['healthy']['events'] + cases['choose_error']['events'][-1:],
                       cases['choose_error']['events'] + cases['healthy']['events'][-1:]):
            with self.subTest(fatal_first='fatal' in events[-2]):
                with heap_messages(events), self.assertRaisesRegex(RuntimeError, 'heap scan unavailable'):
                    K._collect_memory_pairs('synthetic-host', 0, 1)


if __name__ == '__main__':
    unittest.main()
