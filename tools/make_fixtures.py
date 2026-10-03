#!/usr/bin/env python3
"""Generate a synthetic classic mobile QQ database for tests and examples.

Every value here is invented. The owner is account 10000, the friends are 10001 and 10002, the
group is 20001, and the message text is self evidently a fixture. The field cipher uses the
synthetic key SYNTHKEY01234AB, never the real one. A real chat row cannot be produced by this
generator, so pasting a real message in as a shortcut would stand out immediately and would not
survive review.

The output database has the same shape the decoder reads from a real device: a plain SQLite file
whose message tables are named by the uppercase md5 of the peer identifier, whose text messages
carry msgtype -1000, and whose msgData and account columns are XOR obfuscated.

Usage: python make_fixtures.py [out_path]   (default tools/fixtures/synthetic_qq.db)
"""
import hashlib
import copy
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

from qq_field_cipher import encode_field

SYNTH_KEY = b"SYNTHKEY01234AB"   # 15 bytes, obviously not a real key
OWNER = "10000"

# (table_kind, peer_id, [(issend, sender, text, ts)])
CONVERSATIONS = [
    ("friend", "10001", [
        (2, "10000", "这是一条合成的自己发出的短消息", 1700000001),
        (1, "10001", "这是一条合成的对方回复消息，长度稍微长一点用来覆盖多个周期的解码", 1700000002),
        (2, "10000", "好的收到，合成消息用于自检", 1700000003),
    ]),
    ("friend", "10002", [
        (1, "10002", "合成好友二发来的一句话", 1700000101),
        (2, "10000", "回复合成好友二，这里再补一段较长的文本确保跨越十五字节的密钥周期若干次", 1700000102),
    ]),
    ("troop", "20001", [
        (2, "10000", "合成群里自己发的一条", 1700000201),
        (1, "10003", "合成群友发的一条", 1700000202),
    ]),
]


def table_name(kind: str, peer: str) -> str:
    md5 = hashlib.md5(peer.encode()).hexdigest().upper()
    return "mr_%s_%s_New" % (kind, md5)


def build(out_path: str) -> None:
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    db = sqlite3.connect(out_path)
    c = db.cursor()
    uniseq = 1
    for kind, peer, msgs in CONVERSATIONS:
        tn = table_name(kind, peer)
        c.execute(
            "CREATE TABLE '%s' (uniseq INTEGER, msgtype INTEGER, issend INTEGER, "
            "time INTEGER, senderuin BLOB, selfuin BLOB, frienduin BLOB, msgData BLOB)" % tn)
        for issend, sender, text, ts in msgs:
            c.execute(
                "INSERT INTO '%s' (uniseq, msgtype, issend, time, senderuin, selfuin, frienduin, "
                "msgData) VALUES (?,?,?,?,?,?,?,?)" % tn,
                (uniseq, -1000, issend, ts,
                 encode_field(sender.encode(), SYNTH_KEY),
                 encode_field(OWNER.encode(), SYNTH_KEY),
                 encode_field(peer.encode(), SYNTH_KEY),
                 encode_field(text.encode("utf-8"), SYNTH_KEY)))
            uniseq += 1
    db.commit()
    db.close()


def known_pairs():
    """Expected plaintext from the fixed synthetic conversations."""
    return {str(index): row[2] for index, row in enumerate(
        (message for _, _, messages in CONVERSATIONS for message in messages), 1)}


def build_text_variant(out_path, variant):
    """Generate selected-row preservation and metadata failure cases."""
    build(str(out_path))
    text, timestamp = {
        'whitespace': (' \t\n  ', 1700000001),
        'bad_timestamp': (' \t\n  ', 'invalid synthetic timestamp'),
        'normal_bad_timestamp': ('Synthetic normal text', -1),
        'invalid_utf8': (None, 1700000001),
        'empty_selection': (None, 1700000001),
    }[variant]
    with closing(sqlite3.connect(out_path)) as db, db:
        table = table_name('friend', '10001')
        if variant == 'empty_selection':
            for kind, peer, _ in CONVERSATIONS:
                db.execute('UPDATE "'+table_name(kind, peer)+'" SET msgtype=0')
        else:
            blob = encode_field(b'\xff' if text is None else text.encode('utf-8'), SYNTH_KEY)
            db.execute('UPDATE "'+table+'" SET msgData=?,time=? WHERE uniseq=1', (blob, timestamp))
    pairs = known_pairs()
    pairs.pop('1')
    return {'pairs': pairs, 'expected_text': text, 'expected_identity': '1',
            'selected_count': 0 if variant == 'empty_selection' else 7}


def storage_routes():
    """Only invented publication identities and inert configuration values."""
    private = 'https://github.com/example-owner/synthetic-private.git'
    public = 'https://github.com/example-owner/synthetic-public.git'
    cases = {
        'private': {'remotes': {'origin': {'fetch': [private], 'push': [private]}}},
        'public_push': {'remotes': {'origin': {'fetch': [private], 'push': [public]}}},
        'alternate_public': {'remotes': {'origin': {'fetch': [private], 'push': [private]},
                                        'archive': {'fetch': [private], 'push': [public]}}},
        'unknown_push': {'remotes': {'origin': {'fetch': [private], 'push': [private.replace('private', 'unknown')]}}},
        'rewritten_public': {'remotes': {'origin': {'fetch': [private], 'push': [public]}},
                             'config': [('url.'+public+'.pushinsteadof', private)]},
        'rewritten_private': {'remotes': {'origin': {'fetch': [private], 'push': [private]}},
                              'config': [('url.'+private+'.insteadof', 'fixture:')]},
        'canonical_ssh': {'remotes': {'origin': {'fetch': ['git@github.com:example-owner/synthetic-private.git'], 'push': [private]}}},
        'alias_ssh': {'remotes': {'origin': {'fetch': ['git@synthetic-alias:example-owner/synthetic-private.git'], 'push': [private]}}},
    }
    for field in ('core.sshcommand', 'core.gitproxy', 'http.proxy', 'http.curloptresolve',
                  'remote.origin.receivepack', 'remote.origin.proxy', 'remote.origin.vcs', 'core.worktree'):
        cases[field] = {'remotes': copy.deepcopy(cases['private']['remotes']), 'config': [(field, 'synthetic-routing-override')]}
    cases['missing_selected_remote'] = {'remotes': copy.deepcopy(cases['private']['remotes']),
                                        'config': [('remote.pushdefault', 'missing')]}
    return cases


def build_storage_fixture(root):
    """Create a synthetic resolver package and isolated companion paths."""
    root = Path(root)
    tool = root/'tool'
    repo = root/'companion'
    base = repo/'data'
    base.mkdir(parents=True)
    resolver = tool/'guards/tools/datadir.py'
    resolver.parent.mkdir(parents=True)
    resolver.write_text('from pathlib import Path\ndef resolve_data_dir(name):\n    return Path('+repr(str(base))+')\n', encoding='utf-8')
    return tool, repo, base


def storage_environment_cases():
    return {name: 'synthetic-override' for name in (
        'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_CONFIG', 'GIT_CONFIG_GLOBAL',
        'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0',
        'GIT_SSH_COMMAND', 'GIT_PROXY_COMMAND', 'GIT_EXEC_PATH', 'GH_HOST', 'HTTPS_PROXY')}


def build_storage_alias(base, suffix):
    """Generate both names of a synthetic DATA alias inside an isolated fixture root."""
    target = Path(base)/('archive.db'+suffix)
    payload = b'synthetic existing data'
    target.write_bytes(payload)
    alias = Path(base).parent.parent/'synthetic-public-alias'
    os.link(target, alias)
    return alias, payload


def review10_hook(root, hook, source_body, target_kind):
    """Generate a consumer forwarder and an inert delegated guard for native hook checks."""
    root = Path(root)
    path = root / ".githooks" / hook
    path.parent.mkdir(parents=True)
    path.write_bytes(source_body)
    target = root / "guards/hooks" / hook
    target.parent.mkdir(parents=True)
    if target_kind == "directory":
        target.mkdir()
    elif target_kind != "missing":
        body = ("#!/bin/sh\nprintf '%s\\n' synthetic-guard-ran\nprintf 'arg:%s\\n' \"$@\"\n"
                "while IFS= read -r line; do printf 'stdin:%s\\n' \"$line\"; done\n"
                f"exit {7 if target_kind == 'failure' else 0}\n")
        target.write_text("" if target_kind == "empty" else body, encoding="utf-8", newline="\n")
    args = ["synthetic-first", "synthetic two words", "synthetic\\path"]
    stdin = "synthetic input\nsynthetic\\input\n"
    expected = ("synthetic-guard-ran\n" + "".join("arg:%s\n" % arg for arg in args)
                + "".join("stdin:%s\n" % line for line in stdin.splitlines()))
    return {"path": path, "args": args, "stdin": stdin, "expected_stdout": expected,
            "expected_exit": 7 if target_kind == "failure" else 0 if target_kind == "valid" else 1}



def heap_scan_scenarios():
    """Generate heap callbacks and protocol expectations from the synthetic database."""
    pairs = known_pairs()
    observations = [{'uniseq': seq, 'msg': text} for seq, text in pairs.items()]
    scenarios = {}
    for name in ('healthy', 'deferred_healthy', 'choose_error', 'message_read_error',
                 'sequence_read_error', 'enumeration_error', 'perform_error', 'missing_bridge'):
        failed = name not in ('healthy', 'deferred_healthy')
        events = copy.deepcopy(observations) if name not in (
            'enumeration_error', 'perform_error', 'missing_bridge') else []
        events.append({'fatal': 'synthetic heap scan failure'} if failed else {'done': True})
        scenarios[name] = {
            'classes': ['com.tencent.mobileqq.data.MessageForText',
                        'com.tencent.mobileqq.data.MessageForSynthetic'],
            'observations': copy.deepcopy(observations),
            'failure': name if failed else None,
            'deferred': name == 'deferred_healthy',
            'events': events,
            'should_recover': not failed,
        }
    return scenarios



def storage_https_environment_cases():
    """Generate presence, empty-value and case variants of unproved HTTPS overrides."""
    cases = []
    for name in ('SSL_CERT_FILE', 'SSL_CERT_DIR', 'CURL_CA_BUNDLE', 'CURL_SSL_BACKEND'):
        for spelling in (name, name.lower(), name.title()):
            for value in ('synthetic-trust-override', ''):
                cases.append({'name': spelling, 'value': value,
                              'id': spelling + ('-empty' if not value else '-set')})
    return cases


def storage_https_positive_environments():
    """Generate ordinary authentication and inert Git hints without real credentials."""
    return {
        'default': {},
        'auth_and_inert': {'GH_TOKEN': 'synthetic-auth-token', 'GIT_PREFIX': 'data/',
                          'GIT_INDEX_FILE': 'synthetic-index', 'NO_PROXY': 'localhost'},
        'pager': {'GIT_PAGER': 'cat'},
        'pager_commands': {'GIT_PAGER': 'synthetic-unavailable-pager',
                           'GH_PAGER': 'synthetic-unavailable-pager',
                           'PAGER': 'synthetic-unavailable-pager'},
    }

def main():
    import argparse
    ap = argparse.ArgumentParser(description="build a synthetic classic QQ database")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures"),
        help="output directory the fixture database is written into")
    a = ap.parse_args()
    out = os.path.join(a.out, "synthetic_qq.db")
    build(out)
    print("wrote synthetic QQ database ->", out)
    print("owner", OWNER, "key", SYNTH_KEY.decode(), "period", len(SYNTH_KEY))


if __name__ == "__main__":
    main()
