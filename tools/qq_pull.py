#!/usr/bin/env python3
"""Pull a stable classic QQ candidate with checked staging and bounded adb calls.

Temporary device files are created and removed. The source database is never modified.
Account ownership remains unverified until key recovery checks decoded account fields.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import uuid

from qq_database import inspect_database, sha256
from qq_storage import OutputCleanupError, atomic_output, private_path

DB_DIR = '/data/data/com.tencent.mobileqq/databases'


def adb(serial, *args):
    argv = ['adb'] + (['-s', serial] if serial else []) + list(args)
    try:
        result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('adb '+str(args[0])+' unavailable or timed out') from exc
    if result.returncode:
        raise RuntimeError('adb '+str(args[0])+' failed (exit '+str(result.returncode)+')')
    return result


def list_account_dbs(serial):
    result = adb(serial, 'shell', 'ls '+shlex.quote(DB_DIR))
    return sorted(set(line[:-3] for line in result.stdout.splitlines()
                      if re.fullmatch(r'[0-9]{5,20}\.db', line)))


def _source_hash(serial, source):
    result = adb(serial, 'shell', 'sha256sum '+shlex.quote(source))
    words = result.stdout.split()
    if not words or not re.fullmatch(r'[a-fA-F0-9]{64}', words[0]):
        raise RuntimeError('device did not return a valid snapshot hash')
    return words[0].lower()


def _no_live_journal(serial, source):
    adb(serial, 'shell', 'test ! -s '+shlex.quote(source+'-wal')+' && test ! -s '+shlex.quote(source+'-journal'))


def pull_database(serial, uin, output):
    output = private_path(output, artifact_id='database_candidates')
    if output.exists():
        raise FileExistsError('output already exists; select a new candidate path')
    accounts = list_account_dbs(serial)
    uin = uin or (accounts[0] if len(accounts) == 1 else '')
    if not uin or uin not in accounts:
        raise ValueError('select one listed classic QQ account with --uin')
    if adb(serial, 'shell', 'id -u').stdout.strip() != '0':
        raise RuntimeError('adb shell is not root; this client requires existing root access')
    source = DB_DIR+'/'+uin+'.db'
    staging = '/data/local/tmp/qq-export-'+uuid.uuid4().hex+'.db'
    _no_live_journal(serial, source)
    before = _source_hash(serial, source)
    with atomic_output(output) as temporary:
        failure = None
        try:
            adb(serial, 'shell', 'umask 077; cp '+shlex.quote(source)+' '+shlex.quote(staging))
            adb(serial, 'shell', 'chmod 600 '+shlex.quote(staging))
            adb(serial, 'pull', staging, str(temporary))
            _no_live_journal(serial, source)
            if sha256(temporary) != before or _source_hash(serial, source) != before:
                raise RuntimeError('source changed while copying; retry with a stable snapshot')
            inspect_database(temporary)
        except Exception as exc:
            failure = exc
        finally:
            try:
                adb(serial, 'shell', 'rm -f '+shlex.quote(staging))
            except RuntimeError as cleanup_error:
                detail = 'device staging cleanup failed at '+staging
                if failure is not None:
                    detail += '; previous stage failed: '+type(failure).__name__
                raise RuntimeError(detail) from cleanup_error
        if failure is not None:
            raise failure
        if output.exists() or private_path(output, artifact_id='database_candidates') != output:
            raise RuntimeError('candidate destination changed; refusing overwrite')
    return dict(status='pulled_candidate', selected_owner=uin, owner_verified=False,
                ownership_evidence='source_filename_only', database_sha256=before, output=str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', default='')
    parser.add_argument('--uin', default='')
    parser.add_argument('--out', required=True, help='new path inside the private companion data directory')
    args = parser.parse_args()
    try:
        print(json.dumps(pull_database(args.serial, args.uin, args.out)))
    except OutputCleanupError as exc:
        print(json.dumps(exc.receipt), file=sys.stderr)
        return 1
    except (RuntimeError, OSError, ValueError) as exc:
        print('Pull failed: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
