"""Key evidence is distinct from UTF-8 coverage; all bundles contain PRIVATE data."""
import hashlib
import re

from qq_database import inspect_database, message_identity, open_database, sha256, standalone_snapshot, tables
from qq_field_cipher import decode_field, detect_period_from_known_plaintext


def ciphertext_by_uniseq(db_path):
    out = {}
    with open_database(db_path) as db:
        for table, _ in tables(db.cursor()):
            for seq, blob in db.execute('SELECT uniseq,msgData FROM "'+table+'" WHERE msgtype=-1000 AND msgData IS NOT NULL'):
                if not isinstance(blob, bytes):
                    raise ValueError('message data must be a binary field')
                seq = message_identity(seq)
                if seq in out:
                    raise ValueError('ambiguous uniseq across message rows; cannot bind memory evidence')
                out[seq] = (table, blob)
    return out


def validate_accounts(db_path, key, owner):
    if not isinstance(owner, str) or not re.fullmatch(r'[0-9]{5,20}', owner):
        raise ValueError('owner must be an account identifier')
    checked = 0
    with open_database(db_path) as db:
        for table, _ in tables(db.cursor()):
            for selfuin, senderuin, frienduin, sent in db.execute(
                    'SELECT selfuin,senderuin,frienduin,issend FROM "'+table+'" WHERE msgtype=-1000'):
                try:
                    fields = [decode_field(blob, key).decode('ascii') for blob in (selfuin, senderuin, frienduin)]
                except (ValueError, TypeError, UnicodeError) as exc:
                    raise ValueError('account field decoding failed') from exc
                if fields[0] != owner:
                    raise ValueError('owner does not match decoded selfuin')
                if not all(re.fullmatch(r'[0-9]{5,20}', field) for field in fields):
                    raise ValueError('decoded account field is implausible')
                if sent == 2 and fields[1] != owner:
                    raise ValueError('owner-sent row has a different sender')
                checked += 1
    if not checked:
        raise ValueError('insufficient account evidence')
    return checked


def validate_evidence(db_path, bundle):
    with standalone_snapshot(db_path) as snapshot:
        return _validate_evidence(snapshot, bundle)


def _validate_evidence(db_path, bundle):
    if not isinstance(bundle, dict) or type(bundle.get('schema_version')) is not int or bundle['schema_version'] != 1:
        raise ValueError('invalid key evidence schema')
    inspect_database(db_path)
    if bundle.get('database_sha256') != sha256(db_path):
        raise ValueError('key evidence belongs to a different database snapshot')
    try:
        key = bytes.fromhex(bundle['key_hex'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('key evidence is missing a valid key') from exc
    if (not key or len(key) > 64 or type(bundle.get('period')) is not int or bundle['period'] != len(key)
            or bundle.get('key_sha256') != hashlib.sha256(key).hexdigest()):
        raise ValueError('key evidence identity mismatch')
    known = bundle.get('known_pairs')
    if not isinstance(known, list) or len(known) < 2:
        raise ValueError('two independent known plaintext messages are required')
    ciphertext = ciphertext_by_uniseq(db_path)
    identities, messages = set(), set()
    for item in known:
        if not isinstance(item, dict) or not isinstance(item.get('plaintext'), str):
            raise ValueError('malformed known plaintext evidence')
        seq = item.get('uniseq')
        if not isinstance(seq, str) or seq not in ciphertext or seq in identities:
            raise ValueError('known plaintext identity is missing or duplicated')
        table, blob = ciphertext[seq]
        plain = item['plaintext'].encode('utf-8')
        if item.get('table') != table or len(plain) < 2*len(key) or len(plain) != len(blob):
            raise ValueError('known plaintext must bind a complete row and two key periods')
        if detect_period_from_known_plaintext(blob, plain) != key or decode_field(blob, key) != plain:
            raise ValueError('known plaintext does not verify the key')
        identities.add(seq)
        messages.add(plain)
    if len(messages) < 2:
        raise ValueError('independent evidence requires distinct plaintext messages')
    validate_accounts(db_path, key, bundle.get('owner'))
    return key


def evidence_from_pairs(db_path, memory_pairs, owner, max_period=64):
    with standalone_snapshot(db_path) as snapshot:
        return _evidence_from_pairs(snapshot, memory_pairs, owner, max_period)


def _evidence_from_pairs(db_path, memory_pairs, owner, max_period):
    before = sha256(db_path)
    inspect_database(db_path)
    if not isinstance(memory_pairs, dict):
        raise ValueError('memory pairs must be an object')
    ciphertext = ciphertext_by_uniseq(db_path)
    aligned = []
    for seq, text in memory_pairs.items():
        if seq in ciphertext:
            if not isinstance(text, str):
                raise ValueError('memory plaintext must be text')
            table, blob = ciphertext[seq]
            plain = text.encode('utf-8')
            if len(plain) != len(blob):
                raise ValueError('memory and stored message lengths conflict')
            aligned.append((seq, table, text, blob))
    aligned.sort(key=lambda row: -len(row[3]))
    if len(aligned) < 2:
        raise ValueError('insufficient evidence: load two distinct longer messages')
    key = detect_period_from_known_plaintext(aligned[0][3], aligned[0][2].encode('utf-8'), max_period)
    known = []
    for seq, table, text, blob in aligned:
        if decode_field(blob, key) != text.encode('utf-8'):
            raise ValueError('conflicting known plaintext evidence')
        if len(blob) >= 2*len(key):
            known.append(dict(uniseq=seq, table=table, plaintext=text))
    bundle = dict(schema_version=1, database_sha256=before, owner=owner,
                  key_hex=key.hex(), key_sha256=hashlib.sha256(key).hexdigest(), period=len(key), known_pairs=known)
    validate_evidence(db_path, bundle)
    return bundle
