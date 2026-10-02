#!/usr/bin/env python3
"""Check local prerequisites; device reads require the explicit --device option."""
import argparse
import importlib.metadata
import json
import re
import shlex
import shutil
import sys

from qq_pull import adb, list_account_dbs
from qq_storage import private_path


def diagnose(serial='', device=False, server_binary='frida-server'):
    checks = []
    def record(name, ready, detail):
        checks.append(dict(check=name, ready=bool(ready), detail=detail))
    for executable in ('adb', 'git', 'gh'):
        record(executable, shutil.which(executable) is not None, 'executable discovery')
    try:
        version = importlib.metadata.version('frida')
    except importlib.metadata.PackageNotFoundError:
        version = 'missing'
    record('frida-python', version.startswith('16.'), version)
    try:
        private_path('qq_export/doctor-probe')
        record('private-storage', True, 'verified PRIVATE companion; no probe file written')
    except (OSError, RuntimeError, ValueError) as exc:
        record('private-storage', False, str(exc))
    if device:
        try:
            record('device-root', adb(serial, 'shell', 'id -u').stdout.strip() == '0', 'existing root required')
            package = adb(serial, 'shell', 'dumpsys package com.tencent.mobileqq').stdout
            match = re.search(r'\bversionName=([^\s]+)', package)
            client = match.group(1) if match else 'unknown'
            record('classic-client', client.startswith('8.'), client)
            server = adb(serial, 'shell', shlex.quote(server_binary)+' --version').stdout.strip()
            record('frida-server', server == version and server.startswith('16.'), server)
            record('account-database', bool(list_account_dbs(serial)), 'classic account file discovery')
        except RuntimeError as exc:
            record('device-readiness', False, str(exc))
    return dict(status=('device_ready' if device else 'local_ready') if all(c['ready'] for c in checks) else 'not_ready',
                device_checked=device, export_tested=False, checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', action='store_true')
    parser.add_argument('--serial', default='')
    parser.add_argument('--server-binary', default='frida-server')
    args = parser.parse_args()
    result = diagnose(args.serial, args.device, args.server_binary)
    print(json.dumps(result, indent=2))
    return 1 if result['status'] == 'not_ready' else 0


if __name__ == '__main__':
    sys.exit(main())
