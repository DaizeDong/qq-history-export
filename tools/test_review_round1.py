"""Snapshot and transaction regressions, using generated messages only."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

import make_fixtures as F
import qq_database as B
import qq_decode as D
import qq_evidence as E
import qq_keyfind as K
import qq_pull as P
import qq_storage as S
from test_reliability import database, known_pairs


def test_wal_commit_during_export_preserves_old_archive(database, tmp_path, monkeypatch):
    with sqlite3.connect(database) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    writer.close()
    proof = K.evidence_from_pairs(database, known_pairs(), F.OWNER)
    out = tmp_path/'archive.jsonl'
    out.write_bytes(b'previous validated archive\n')
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    original = D.decode_db
    writer = None

    def interleave(*args):
        nonlocal writer
        rows = original(*args)
        yield next(rows)
        writer = sqlite3.connect(database)
        table = B.tables(writer.cursor())[1][0]
        writer.execute('INSERT INTO "'+table+'" '
                       '(uniseq,msgtype,issend,time,senderuin,selfuin,frienduin,msgData) '
                       'VALUES (?,?,?,?,?,?,?,?)',
                       (999, -1000, 1, 1700000999, F.encode_field(b'99999', F.SYNTH_KEY),
                        F.encode_field(b'99999', F.SYNTH_KEY), F.encode_field(b'10001', F.SYNTH_KEY),
                        F.encode_field(b'Synthetic late row from a different account.', F.SYNTH_KEY)))
        writer.commit()
        yield from rows

    monkeypatch.setattr(D, 'decode_db', interleave)
    try:
        with pytest.raises((ValueError, RuntimeError), match='journal|changed'):
            D.export_database(database, proof, out)
        assert out.read_bytes() == b'previous validated archive\n'
    finally:
        if writer is not None:
            writer.close()


@pytest.mark.parametrize('suffix', ['-wal', '-journal', '-shm'])
def test_export_cannot_occupy_database_sidecars(database, monkeypatch, suffix):
    proof = K.evidence_from_pairs(database, known_pairs(), F.OWNER)
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    out = Path(str(database)+suffix)
    with pytest.raises(ValueError, match='input|sidecar|database'):
        D.export_database(database, proof, out)
    assert not out.exists()


@pytest.mark.parametrize('suffix', ['-wal', '-journal', '-shm'])
def test_recovery_cannot_occupy_database_sidecars_before_device_access(database, monkeypatch, suffix):
    monkeypatch.setattr(K, 'private_path', lambda p: Path(p))
    monkeypatch.setattr(K, 'recover_key', lambda *a: pytest.fail('unexpected device access'))
    monkeypatch.setattr(sys, 'argv', ['qq_keyfind.py', '--db', str(database), '--owner', F.OWNER,
                                    '--out', str(database)+suffix])
    assert K.main() == 1


def test_output_lock_cannot_replace_database_input(database, tmp_path, monkeypatch):
    source = tmp_path/'archive.lock'
    database.rename(source)
    proof = K.evidence_from_pairs(source, known_pairs(), F.OWNER)
    monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
    with pytest.raises(ValueError, match='input|database'):
        D.export_database(source, proof, tmp_path/'archive')


@pytest.mark.parametrize('identity', [None, 'not-an-id', '', 1.5])
def test_every_text_row_requires_a_numeric_message_identity(database, identity):
    with sqlite3.connect(database) as writer:
        changed = sum(writer.execute('UPDATE "'+table+'" SET uniseq=? WHERE uniseq=1',
                                     (identity,)).rowcount for table, _ in B.tables(writer.cursor()))
        assert changed == 1
    writer.close()
    pairs = known_pairs()
    pairs.pop('1')
    with pytest.raises(ValueError, match='identity|uniseq'):
        K.evidence_from_pairs(database, pairs, F.OWNER)


@pytest.mark.parametrize('identity', [-(2**63), 0, 2**63-1, '-12', '0012'])
def test_supported_long_message_identities_are_canonical(identity):
    assert B.message_identity(identity) == str(int(identity))


@pytest.mark.parametrize('identity', [-(2**63)-1, 2**63, '9'*5000, True])
def test_invalid_long_identity_domain_is_rejected(identity):
    with pytest.raises(ValueError, match='identity|uniseq'):
        B.message_identity(identity)


def test_reading_checkpointed_wal_input_does_not_create_sidecars(database):
    with sqlite3.connect(database) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
    writer.close()
    before = sorted(p.name for p in database.parent.iterdir())
    B.inspect_database(database)
    assert sorted(p.name for p in database.parent.iterdir()) == before


def test_committed_output_has_explicit_receipt_if_lock_cleanup_fails(tmp_path, monkeypatch):
    out = tmp_path/'archive.jsonl'
    out.write_bytes(b'old')
    unlink = Path.unlink

    def deny_lock(path, *args, **kwargs):
        if path == out.with_name(out.name+'.lock'):
            raise PermissionError('synthetic cleanup denial')
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', deny_lock)
    with pytest.raises(RuntimeError) as caught:
        with S.atomic_output(out) as temporary:
            temporary.write_bytes(b'new')
    assert out.read_bytes() == b'new'
    assert caught.value.receipt['committed'] is True
    assert caught.value.receipt['status'] == 'committed_cleanup_required'
    assert caught.value.receipt['output'] == str(out)


def test_prepromotion_error_and_cleanup_failure_preserve_old_archive(tmp_path, monkeypatch):
    out = tmp_path/'archive.jsonl'
    out.write_bytes(b'old')
    unlink = Path.unlink

    def deny_lock(path, *args, **kwargs):
        if path == out.with_name(out.name+'.lock'):
            raise PermissionError('synthetic cleanup denial')
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', deny_lock)
    with pytest.raises(RuntimeError) as caught:
        with S.atomic_output(out) as temporary:
            temporary.write_bytes(b'partial')
            raise ValueError('synthetic precommit failure')
    assert out.read_bytes() == b'old'
    assert caught.value.receipt['committed'] is False
    assert caught.value.receipt['status'] == 'failed_cleanup_required'


def test_recovery_rejects_database_change_after_account_validation(database, monkeypatch):
    validate = E.validate_accounts

    def mutate(*args):
        result = validate(*args)
        with sqlite3.connect(database) as writer:
            table = B.tables(writer.cursor())[0][0]
            writer.execute('UPDATE "'+table+'" SET time=time+1')
        writer.close()
        return result

    monkeypatch.setattr(E, 'validate_accounts', mutate)
    with pytest.raises(ValueError, match='changed'):
        K.evidence_from_pairs(database, known_pairs(), F.OWNER)


@pytest.mark.parametrize('command', ['pull', 'recover', 'decode'])
def test_cli_reports_committed_cleanup_receipt(command, tmp_path, monkeypatch, capsys):
    out = tmp_path/'archive.jsonl'
    error = S.OutputCleanupError(out, True, [(Path(str(out)+'.lock'), PermissionError())], None)

    def fail(*args):
        raise error

    if command == 'pull':
        monkeypatch.setattr(P, 'pull_database', fail)
        monkeypatch.setattr(sys, 'argv', ['qq_pull.py', '--out', str(out)])
        main = P.main
    elif command == 'recover':
        monkeypatch.setattr(K, 'private_path', lambda p: Path(p))
        monkeypatch.setattr(K, 'recover_key', fail)
        monkeypatch.setattr(sys, 'argv', ['qq_keyfind.py', '--out', str(out),
                                        '--db', str(tmp_path/'source.db'), '--owner', F.OWNER])
        main = K.main
    else:
        evidence = tmp_path/'evidence.json'
        evidence.write_text('{}')
        monkeypatch.setattr(D, 'private_path', lambda p: Path(p))
        monkeypatch.setattr(D, 'export_database', fail)
        monkeypatch.setattr(sys, 'argv', ['qq_decode.py', '--out', str(out),
                                        '--db', str(tmp_path/'source.db'), '--evidence', str(evidence)])
        main = D.main
    assert main() == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err) == error.receipt
