#!/usr/bin/env python3
"""Verify key/account evidence and atomically export classic QQ text messages."""
import argparse
import json
import sys

from qq_database import message_identity, open_database, sha256, standalone_snapshot, tables as _tables
from qq_evidence import validate_evidence
from qq_field_cipher import decode_field
from qq_storage import OutputCleanupError, atomic_output, private_path, reject_input_alias

TEXT_MSGTYPE = -1000


def _dec_text(blob, key):
    if not blob:
        return None
    try:
        return decode_field(bytes(blob), key).decode('utf-8')
    except UnicodeDecodeError:
        return None


def decode_db(db_path, key, owner_uin):
    """Low-level read-only iterator; callers must establish key/account evidence."""
    with open_database(db_path) as db:
        for table, ctx in _tables(db.cursor()):
            conv = 'qq_'+table.split('_')[2][:12]
            query = ('SELECT issend,msgData,senderuin,time,uniseq FROM "'+table+'" '
                     'WHERE msgtype=? AND msgData IS NOT NULL ORDER BY time,uniseq')
            for sent, blob, sender_blob, timestamp, seq in db.execute(query, (TEXT_MSGTYPE,)):
                text = _dec_text(blob, key)
                if text is None:
                    raise ValueError('text message failed UTF-8 decoding; refusing a partial export')
                if type(timestamp) is not int or timestamp < 0:
                    raise ValueError('message timestamp is invalid')
                sender = _dec_text(sender_blob, key)
                is_me = sent == 2 or sender == owner_uin
                yield dict(text=text, is_me=bool(is_me), ctx=ctx, ts=timestamp,
                           sender='qq_me' if is_me else 'qq_'+(sender or 'unknown'), conv=conv, uniseq=message_identity(seq))


def decode_rate(db_path, key):
    """UTF-8 decoding coverage only; an incorrect ASCII key can also score 1.0."""
    total = valid = 0
    with open_database(db_path) as db:
        for table, _ in _tables(db.cursor()):
            for (blob,) in db.execute('SELECT msgData FROM "'+table+'" WHERE msgtype=-1000 AND msgData IS NOT NULL'):
                if blob:
                    total += 1
                    valid += _dec_text(blob, key) is not None
    return valid/total if total else 0.0


def export_database(db_path, bundle, output):
    output = private_path(output, artifact_id='selected_exports')
    reject_input_alias(output, [db_path], database=db_path)
    count = mine = 0
    with atomic_output(output) as temporary:
        with standalone_snapshot(db_path) as snapshot:
            before = sha256(snapshot)
            key = validate_evidence(snapshot, bundle)
            coverage = decode_rate(snapshot, key)
            if coverage != 1.0:
                raise ValueError('incomplete decoding coverage; existing export is preserved')
            with temporary.open('w', encoding='utf-8', newline='\n') as stream:
                for record in decode_db(snapshot, key, bundle['owner']):
                    stream.write(json.dumps(record, ensure_ascii=False)+'\n')
                    count += 1
                    mine += record['is_me']
            if not count:
                raise ValueError('empty export')
        if private_path(output, artifact_id='selected_exports') != output:
            raise ValueError('output destination changed during export')
    return dict(exported=count, owner_messages=mine, decoding_coverage=coverage,
                owner_verified=True, key_evidence='known_plaintext_verified', database_sha256=before, output=str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--evidence', required=True, help='private recovery bundle from qq_keyfind.py')
    parser.add_argument('--out', required=True, help='path inside the verified private companion data directory')
    args = parser.parse_args()
    try:
        db = private_path(args.db)
        evidence = private_path(args.evidence)
        out = private_path(args.out, artifact_id='selected_exports')
        reject_input_alias(out, [db, evidence], database=db)
        bundle = json.loads(evidence.read_text(encoding='utf-8'))
        print(json.dumps(export_database(db, bundle, out)))
    except OutputCleanupError as exc:
        print(json.dumps(exc.receipt), file=sys.stderr)
        return 1
    except (RuntimeError, OSError, ValueError) as exc:
        print('Decode failed: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
