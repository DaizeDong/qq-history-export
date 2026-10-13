"""Generated business regressions for the storage boundary and exact text preservation."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import make_fixtures as F
import qq_decode as D
import qq_keyfind as K
import qq_pull as P
import qq_storage as S


class StorageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @contextlib.contextmanager
    def storage(self):
        with tempfile.TemporaryDirectory(prefix='qq-route-fixture-') as directory:
            tool, repo, base = F.build_storage_fixture(directory)
            with patch.object(S, 'ROOT', tool), patch.dict(
                    os.environ, {'QQ_HISTORY_EXPORT_DATA_DIR': str(base)}):
                yield base

    def test_plain_companion_write_needs_no_publication_proof(self):
        with self.storage() as base:
            self.assertEqual(S.write_bundle('evidence.json', {'synthetic': True}), base.resolve()/'evidence.json')
            self.assertEqual(json.loads((base/'evidence.json').read_text()), {'synthetic': True})

    def test_missing_companion_precedes_device_or_heap_access(self):
        with self.storage() as base:
            base.rmdir()
            with patch.object(P, 'adb', side_effect=AssertionError('device was reached')):
                with self.assertRaises(RuntimeError):
                    P.pull_database('', F.OWNER, 'candidate.db')
            with patch.object(K, 'recover_key', side_effect=AssertionError('heap was reached')), patch.object(
                    sys, 'argv', ['qq_keyfind.py', '--db', 'candidate.db', '--owner', F.OWNER, '--out', 'evidence.json']):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(K.main(), 1)
            self.assertFalse(base.exists())

    def test_physical_data_and_sidecar_aliases_refuse(self):
        for suffix in ('', '.lock', '-wal', '-journal', '-shm'):
            with self.subTest(suffix=suffix), self.storage() as base:
                public_alias, payload = F.build_storage_alias(base, suffix)
                with self.assertRaisesRegex(RuntimeError, 'link|alias'):
                    S.private_path('archive.db')
                self.assertEqual(public_alias.read_bytes(), payload)

    def test_explicit_escape_refuses(self):
        with self.storage() as base:
            with self.assertRaises(RuntimeError):
                S.private_path(base.parent/'escape.json')


class TextPreservationTests(unittest.TestCase):
    def test_whitespace_selected_row_keeps_exact_text_and_identity(self):
        with tempfile.TemporaryDirectory(prefix='qq-text-fixture-') as directory:
            root = Path(directory)
            db, evidence, output = root/'synthetic.db', root/'evidence.json', root/'messages.jsonl'
            case = F.build_text_variant(db, 'whitespace')
            bundle = K.evidence_from_pairs(db, case['pairs'], F.OWNER)
            evidence.write_text(json.dumps(bundle), encoding='utf-8')
            stdout = io.StringIO()
            with patch.object(D, 'private_path', lambda value, **kwargs: Path(value)), patch.object(
                    S, 'private_path', lambda value, **kwargs: Path(value)), patch.object(sys, 'argv', [
                    'qq_decode.py', '--db', str(db), '--evidence', str(evidence), '--out', str(output)]), contextlib.redirect_stdout(stdout):
                self.assertEqual(D.main(), 0)
            rows = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
            expected = F.known_pairs()
            expected[case['expected_identity']] = case['expected_text']
            self.assertEqual({row['uniseq']: row['text'] for row in rows}, expected)
            receipt = json.loads(stdout.getvalue())
            self.assertEqual(receipt['exported'], case['selected_count'])
            self.assertEqual(receipt['decoding_coverage'], 1.0)

    def test_invalid_selected_rows_preserve_old_archive(self):
        for variant in ('bad_timestamp', 'normal_bad_timestamp', 'invalid_utf8', 'empty_selection'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory(prefix='qq-invalid-fixture-') as directory:
                root = Path(directory)
                db, evidence, output = root/'synthetic.db', root/'evidence.json', root/'messages.jsonl'
                case = F.build_text_variant(db, variant)
                if variant == 'empty_selection':
                    bundle = {}
                else:
                    bundle = K.evidence_from_pairs(db, case['pairs'], F.OWNER)
                evidence.write_text(json.dumps(bundle), encoding='utf-8')
                output.write_bytes(b'previous synthetic archive\n')
                with patch.object(D, 'private_path', lambda value, **kwargs: Path(value)), patch.object(sys, 'argv', [
                        'qq_decode.py', '--db', str(db), '--evidence', str(evidence), '--out', str(output)]), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(D.main(), 1)
                self.assertEqual(output.read_bytes(), b'previous synthetic archive\n')
                self.assertFalse(list(root.glob('*.lock')))
                self.assertFalse(list(root.glob('*.partial')))


if __name__ == '__main__':
    unittest.main()
