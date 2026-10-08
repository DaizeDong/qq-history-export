#!/usr/bin/env python3
"""Recover a classic QQ field key from independent known plaintext observations.

The bundle is private data containing the key and message evidence. UTF-8 coverage
is reported separately and never used as proof that a key is correct.
"""
import argparse
import json
import sys
import time

from qq_database import inspect_database, standalone_snapshot
from qq_decode import decode_rate
from qq_evidence import evidence_from_pairs
from qq_storage import OutputCleanupError, private_path, reject_input_alias, write_bundle

MAIN_PROCESS = 'com.tencent.mobileqq'

JS = r"""
var failed = false;
function failScan(stage) {
  if (!failed) {
    failed = true;
    send({fatal: "Heap scan failed: " + stage});
  }
}
if (typeof Java === 'undefined') {
  failScan("Java bridge missing. Use frida 16.x; frida 17 dropped the built in Java bridge.");
} else {
  try {
    Java.perform(function () {
      var subs = [];
      try {
        Java.enumerateLoadedClasses({
          onMatch: function (n) {
            if (/com\.tencent\.mobileqq\.data\.MessageFor[A-Za-z]+$/.test(n)) subs.push(n);
          },
          onComplete: function () {
            var remaining = subs.length;
            var startedAll = false;
            function finishScan() {
              if (!failed && startedAll && remaining === 0) send({done: true});
            }
            subs.forEach(function (cn) {
              if (failed) return;
              try {
                Java.choose(cn, {
                  onMatch: function (inst) {
                    if (failed) return;
                    try {
                      var msg = inst.msg.value;
                      if (msg && msg.length > 0) {
                        send({uniseq: inst.uniseq.value.toString(), msg: msg});
                      }
                    } catch (e) {
                      failScan("selected message field read");
                    }
                  },
                  onComplete: function () {
                    remaining -= 1;
                    finishScan();
                  }
                });
              } catch (e) {
                failScan("selected class scan");
              }
            });
            startedAll = true;
            finishScan();
          }
        });
      } catch (e) {
        failScan("class enumeration");
      }
    });
  } catch (e) {
    failScan("Java callback setup");
  }
}
"""


def _collect_memory_pairs(host, pid, seconds):
    import frida
    if not str(frida.__version__).startswith('16.'):
        raise RuntimeError('This bundled agent requires Frida 16.x with the Java bridge')
    if type(seconds) is not int or not 1 <= seconds <= 120:
        raise ValueError('seconds must be between 1 and 120')
    device = frida.get_device_manager().add_remote_device(host)
    session = device.attach(pid or MAIN_PROCESS)
    pairs = {}
    state = {'done': False, 'fatal': None}
    try:
        script = session.create_script(JS)
        def on_message(message, data):
            if message.get('type') == 'send':
                payload = message.get('payload', {})
                if payload.get('fatal'):
                    state['fatal'] = 'Java bridge or heap scan unavailable'
                elif payload.get('done'):
                    state['done'] = True
                elif payload.get('uniseq'):
                    seq, text = str(payload['uniseq']), payload.get('msg')
                    if not isinstance(text, str) or seq in pairs and pairs[seq] != text:
                        state['fatal'] = 'ambiguous memory message identity'
                    else:
                        pairs[seq] = text
            elif message.get('type') == 'error':
                state['fatal'] = 'injected heap scan failed'
        script.on('message', on_message)
        script.load()
        deadline = time.monotonic()+seconds
        while not state['done'] and not state['fatal'] and time.monotonic() < deadline:
            time.sleep(0.1)
        if state['fatal'] or not state['done']:
            raise RuntimeError(state['fatal'] or 'heap scan did not complete before deadline')
        return pairs
    finally:
        session.detach()


def recover_key(db_path, owner, host='127.0.0.1:27044', pid=0, seconds=20, max_period=64):
    with standalone_snapshot(db_path) as snapshot:
        inspect_database(snapshot)
        pairs = _collect_memory_pairs(host, pid, seconds)
        bundle = evidence_from_pairs(snapshot, pairs, owner, max_period)
        bundle['decoding_coverage'] = decode_rate(snapshot, bytes.fromhex(bundle['key_hex']))
        bundle['observation_source'] = 'running_client_heap'
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--out', required=True, help='private key/evidence JSON bundle')
    parser.add_argument('--host', default='127.0.0.1:27044')
    parser.add_argument('--pid', type=int, default=0)
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    try:
        db = private_path(args.db)
        output = private_path(args.out, artifact_id='recovery_evidence')
        reject_input_alias(output, [db], database=db)
        bundle = recover_key(db, args.owner, args.host, args.pid, args.seconds)
        write_bundle(output, bundle)
        print(json.dumps(dict(status='known_plaintext_verified', owner_verified=True,
                              period=bundle['period'], matched_pairs=len(bundle['known_pairs']),
                              decoding_coverage=bundle['decoding_coverage'], evidence=str(output))))
    except OutputCleanupError as exc:
        print(json.dumps(exc.receipt), file=sys.stderr)
        return 1
    except (RuntimeError, OSError, ValueError, ImportError) as exc:
        print('Recovery failed: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
