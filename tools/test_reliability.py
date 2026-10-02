"""Offline reliability cases; every fixture is generated, all adb calls are intercepted."""
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

import make_fixtures as F
import qq_decode as D
import qq_keyfind as K
import qq_pull as P
from qq_field_cipher import detect_period_from_known_plaintext, encode_field


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'synthetic.db'
    F.build(str(path))
    return path


def known_pairs():
    pairs = {}
    seq = 0
    for _, _, messages in F.CONVERSATIONS:
        for _, _, text, _ in messages:
            seq += 1
            pairs[str(seq)] = text
    return pairs


def test_short_sample_cannot_establish_a_period():
    with pytest.raises(ValueError):
        detect_period_from_known_plaintext(b'A', b'a', max_period=1)


def test_valid_key_bundle_and_atomic_export(database, tmp_path, monkeypatch):
    bundle = K.evidence_from_pairs(database, known_pairs(), F.OWNER)
    out = tmp_path / 'messages.jsonl'
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    result = D.export_database(database, bundle, out)
    records = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    assert len(records) == 7 and result['owner_verified'] is True
    assert result['decoding_coverage'] == 1.0


@pytest.mark.parametrize('mutation', ['wrong_key', 'wrong_owner', 'changed_db', 'single_pair', 'duplicate_pair'])
def test_invalid_evidence_preserves_previous_export(database, tmp_path, monkeypatch, mutation):
    bundle = K.evidence_from_pairs(database, known_pairs(), F.OWNER)
    if mutation == 'wrong_key':
        bundle['key_hex'] = b'WRONGKEY'.hex()
    elif mutation == 'wrong_owner':
        bundle['owner'] = '10009'
    elif mutation == 'changed_db':
        bundle['database_sha256'] = '0'*64
    elif mutation == 'single_pair':
        bundle['known_pairs'] = bundle['known_pairs'][:1]
    else:
        bundle['known_pairs'] = [bundle['known_pairs'][0]]*2
    out = tmp_path / 'messages.jsonl'
    out.write_bytes(b'previous validated archive\n')
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    with pytest.raises((ValueError, RuntimeError)):
        D.export_database(database, bundle, out)
    assert out.read_bytes() == b'previous validated archive\n'


def test_ascii_decoding_coverage_does_not_prove_key(database):
    # A one-byte XOR error leaves ASCII messages as valid UTF-8.
    db = sqlite3.connect(database)
    for table, _ in D._tables(db.cursor()):
        db.execute('UPDATE "'+table+'" SET msgData=?', (encode_field(b'Synthetic ASCII message only', F.SYNTH_KEY),))
    db.commit(); db.close()
    wrong = bytes(c ^ 1 for c in F.SYNTH_KEY)
    assert D.decode_rate(str(database), wrong) == 1.0
    with pytest.raises(ValueError):
        K.evidence_from_pairs(database, {'1': 'Synthetic ASCII message only'}, F.OWNER)


def test_wrong_account_rejected_from_decoded_fields(database):
    with pytest.raises(ValueError, match='owner'):
        K.evidence_from_pairs(database, known_pairs(), '10009')


def test_recovery_rejects_conflicting_long_pairs(database):
    pairs = known_pairs()
    pairs['2'] = 'A different synthetic long message that cannot match the stored field.'
    with pytest.raises(ValueError):
        K.evidence_from_pairs(database, pairs, F.OWNER)


def test_duplicate_uniseq_is_not_silently_reassigned(database):
    db = sqlite3.connect(database)
    tables = D._tables(db.cursor())
    db.execute('UPDATE "'+tables[1][0]+'" SET uniseq=1')
    db.commit(); db.close()
    with pytest.raises(ValueError, match='ambiguous'):
        K.evidence_from_pairs(database, known_pairs(), F.OWNER)


def test_missing_db_read_does_not_create_an_empty_database(tmp_path):
    missing = tmp_path / 'absent.db'
    with pytest.raises((ValueError, sqlite3.Error)):
        list(D.decode_db(str(missing), F.SYNTH_KEY, F.OWNER))
    assert not missing.exists()


def test_adb_failure_and_timeout_are_checked(monkeypatch):
    monkeypatch.setattr(P.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 1, '', 'synthetic failure'))
    with pytest.raises(RuntimeError):
        P.adb('', 'shell', 'id')
    def timed_out(argv, **kwargs):
        assert 0 < kwargs['timeout'] <= 120
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
    monkeypatch.setattr(P.subprocess, 'run', timed_out)
    with pytest.raises(RuntimeError):
        P.adb('', 'shell', 'id')


def test_pull_existing_output_is_never_used_as_new_success(tmp_path, monkeypatch):
    out = tmp_path / 'old.db'
    out.write_bytes(b'X'*4096)
    monkeypatch.setattr(P, 'private_path', lambda p: Path(p))
    monkeypatch.setattr(P, 'adb', lambda *a: pytest.fail('existing output must fail before device access'))
    with pytest.raises((RuntimeError, ValueError, FileExistsError)):
        P.pull_database('', F.OWNER, out)
    assert out.read_bytes() == b'X'*4096


@pytest.mark.parametrize('failure', ['copy', 'chmod', 'pull', 'cleanup'])
def test_failed_pull_cleans_staging_and_never_promotes(tmp_path, database, monkeypatch, failure):
    out = tmp_path / 'new.db'
    calls = []
    monkeypatch.setattr(P, 'private_path', lambda p: Path(p))
    def fake(serial, *args):
        calls.append(args)
        command = ' '.join(map(str, args))
        if args[0] == 'pull':
            Path(args[-1]).write_bytes(database.read_bytes())
            stage = 'pull'
        elif 'cp ' in command:
            stage = 'copy'
        elif 'chmod ' in command:
            stage = 'chmod'
        elif 'rm -f ' in command:
            stage = 'cleanup'
        else:
            stage = 'other'
        if stage == failure:
            raise RuntimeError('synthetic '+stage+' failure')
        if 'ls ' in command:
            stdout = F.OWNER+'.db\n'
        elif 'sha256sum ' in command:
            import hashlib
            stdout = hashlib.sha256(database.read_bytes()).hexdigest()+'  synthetic.db\n'
        else:
            stdout = '0\n'
        return subprocess.CompletedProcess(args, 0, stdout, '')
    monkeypatch.setattr(P, 'adb', fake)
    with pytest.raises(RuntimeError):
        P.pull_database('', F.OWNER, out)
    assert not out.exists()
    assert any('rm -f ' in ' '.join(map(str, call)) for call in calls)


def test_completed_pull_is_a_new_unverified_candidate(tmp_path, database, monkeypatch):
    import hashlib
    out = tmp_path / 'candidate.db'
    calls = []
    monkeypatch.setattr(P, 'private_path', lambda p: Path(p))
    def fake(serial, *args):
        calls.append(args)
        command = ' '.join(args)
        if args[0] == 'pull':
            Path(args[-1]).write_bytes(database.read_bytes())
        value = (F.OWNER+'.db\n' if 'ls ' in command else
                 hashlib.sha256(database.read_bytes()).hexdigest()+'  synthetic.db\n'
                 if 'sha256sum ' in command else '0\n')
        return subprocess.CompletedProcess(args, 0, value, '')
    monkeypatch.setattr(P, 'adb', fake)
    result = P.pull_database('', F.OWNER, out)
    assert out.read_bytes() == database.read_bytes()
    assert result['status'] == 'pulled_candidate' and result['owner_verified'] is False
    assert any('chmod 600 ' in ' '.join(call) for call in calls)
    assert not list(tmp_path.glob('*.partial')) and not list(tmp_path.glob('*.lock'))


def test_exception_mid_export_preserves_old_archive(database, tmp_path, monkeypatch):
    bundle = K.evidence_from_pairs(database, known_pairs(), F.OWNER)
    out = tmp_path/'messages.jsonl'
    out.write_bytes(b'previous validated archive\n')
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    original = D.decode_db
    def broken(*args):
        yield next(original(*args))
        raise RuntimeError('synthetic interrupted decoder')
    monkeypatch.setattr(D, 'decode_db', broken)
    with pytest.raises(RuntimeError):
        D.export_database(database, bundle, out)
    assert out.read_bytes() == b'previous validated archive\n'
    assert not list(tmp_path.glob('*.partial')) and not list(tmp_path.glob('*.lock'))


def test_unsupported_schema_and_live_journal_fail(database):
    from qq_database import inspect_database
    wal = Path(str(database)+'-wal')
    wal.write_bytes(b'synthetic active journal')
    with pytest.raises(ValueError, match='journal'):
        inspect_database(database)
    wal.unlink()
    db = sqlite3.connect(database)
    db.execute('CREATE TABLE mr_friend_malformed(x)')
    db.commit(); db.close()
    with pytest.raises(ValueError, match='table'):
        inspect_database(database)


@pytest.mark.parametrize('visibility', ['false', '', 'null'])
def test_public_or_unknown_storage_is_rejected(tmp_path, monkeypatch, visibility):
    import qq_storage as S
    tool, repo, base = F.build_storage_fixture(tmp_path)
    monkeypatch.setattr(S, 'ROOT', tool)
    monkeypatch.setenv('QQ_HISTORY_EXPORT_DATA_DIR', str(base))
    def run(argv):
        if argv[0] == 'gh':
            return visibility
        if '--show-toplevel' in argv:
            return str(repo)
        if 'config' in argv:
            return ''
        if argv[-1] == 'remote':
            return 'origin'
        return 'https://github.com/example/synthetic-config.git'
    monkeypatch.setattr(S, '_run', run)
    with pytest.raises(RuntimeError, match='PUBLIC|unknown'):
        S.private_path(base/'candidate.db')


def test_private_storage_allows_named_companion_and_rejects_escape(tmp_path, monkeypatch):
    import qq_storage as S
    tool, repo, base = F.build_storage_fixture(tmp_path)
    monkeypatch.setattr(S, 'ROOT', tool)
    monkeypatch.setenv('QQ_HISTORY_EXPORT_DATA_DIR', str(base))
    def run(argv):
        if argv[0] == 'gh':
            return 'true'
        if '--show-toplevel' in argv:
            return str(repo)
        if 'config' in argv:
            return ''
        if argv[-1] == 'remote':
            return 'origin'
        return 'https://github.com/example/synthetic-config.git'
    monkeypatch.setattr(S, '_run', run)
    assert S.private_path('candidate.db') == base/'candidate.db'
    with pytest.raises(RuntimeError):
        S.private_path(tmp_path/'escape.db')


def test_frida_load_failure_always_detaches(monkeypatch):
    import sys
    from types import SimpleNamespace
    detached = []
    def fail():
        raise RuntimeError('synthetic script load failure')
    script = SimpleNamespace(on=lambda *a: None, load=fail)
    session = SimpleNamespace(create_script=lambda *a: script, detach=lambda: detached.append(True))
    device = SimpleNamespace(attach=lambda *a: session)
    frida = SimpleNamespace(__version__='16.0.0', get_device_manager=lambda: SimpleNamespace(add_remote_device=lambda *a: device))
    monkeypatch.setitem(sys.modules, 'frida', frida)
    with pytest.raises(RuntimeError, match='load'):
        K._collect_memory_pairs('synthetic', 0, 1)
    assert detached == [True]


def test_three_cli_stages_use_selected_private_root(database, tmp_path, monkeypatch, capsys):
    import hashlib
    import sys
    import qq_storage as S
    tool, repo, base = F.build_storage_fixture(tmp_path)
    monkeypatch.setattr(S, 'ROOT', tool)
    monkeypatch.setenv('QQ_HISTORY_EXPORT_DATA_DIR', str(base))
    def storage_command(argv):
        if argv[0] == 'gh':
            return 'true'
        if '--show-toplevel' in argv:
            return str(repo)
        if 'config' in argv:
            return ''
        if argv[-1] == 'remote':
            return 'origin'
        return 'https://github.com/example/synthetic-companion.git'
    monkeypatch.setattr(S, '_run', storage_command)
    def fake_adb(serial, *args):
        command = ' '.join(args)
        if args[0] == 'pull':
            Path(args[-1]).write_bytes(database.read_bytes())
        value = (F.OWNER+'.db\n' if 'ls ' in command else
                 hashlib.sha256(database.read_bytes()).hexdigest()+'  synthetic.db\n'
                 if 'sha256sum ' in command else '0\n')
        return subprocess.CompletedProcess(args, 0, value, '')
    monkeypatch.setattr(P, 'adb', fake_adb)
    monkeypatch.setattr(K, '_collect_memory_pairs', lambda *args: known_pairs())
    monkeypatch.setattr(sys, 'argv', ['qq_pull.py', '--uin', F.OWNER, '--out', 'pull/candidate.db'])
    assert P.main() == 0
    monkeypatch.setattr(sys, 'argv', ['qq_keyfind.py', '--db', 'pull/candidate.db', '--owner', F.OWNER,
                                     '--out', 'keys/recovery.json'])
    assert K.main() == 0
    monkeypatch.setattr(sys, 'argv', ['qq_decode.py', '--db', 'pull/candidate.db', '--evidence',
                                     'keys/recovery.json', '--out', 'messages.jsonl'])
    assert D.main() == 0
    output = capsys.readouterr().out
    assert F.SYNTH_KEY.decode() not in output and F.SYNTH_KEY.hex() not in output
    assert len((base/'messages.jsonl').read_text(encoding='utf-8').splitlines()) == 7


def test_local_doctor_never_contacts_device(monkeypatch, tmp_path):
    import qq_doctor as Q
    monkeypatch.setattr(Q.shutil, 'which', lambda name: '/synthetic/'+name)
    monkeypatch.setattr(Q.importlib.metadata, 'version', lambda name: '16.1.0')
    monkeypatch.setattr(Q, 'private_path', lambda path: tmp_path/path)
    monkeypatch.setattr(Q, 'adb', lambda *a: pytest.fail('unexpected device access'))
    result = Q.diagnose()
    assert result['status'] == 'local_ready' and not result['device_checked'] and not result['export_tested']


def test_doctor_rejects_unmatched_server_and_nt(monkeypatch, tmp_path):
    import qq_doctor as Q
    monkeypatch.setattr(Q.shutil, 'which', lambda name: '/synthetic/'+name)
    monkeypatch.setattr(Q.importlib.metadata, 'version', lambda name: '16.1.0')
    monkeypatch.setattr(Q, 'private_path', lambda path: tmp_path/path)
    def fake(*args):
        cmd = args[-1]
        stdout = 'versionName=9.0' if 'dumpsys' in cmd else '17.0.0' if '--version' in cmd else '0'
        return subprocess.CompletedProcess(args, 0, stdout, '')
    monkeypatch.setattr(Q, 'adb', fake)
    monkeypatch.setattr(Q, 'list_account_dbs', lambda serial: [F.OWNER])
    result = Q.diagnose(device=True)
    assert result['status'] == 'not_ready'
    assert {row['check'] for row in result['checks'] if not row['ready']} == {'classic-client', 'frida-server'}
