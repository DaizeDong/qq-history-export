# Classic QQ export workflow

Start with a separately cloned PRIVATE companion, create its data directory, and point
`QQ_HISTORY_EXPORT_CONFIG` to that clone. An explicit invalid pointer fails; there is
no public or unversioned fallback. The selected companion must contain `data/`;
DATA_DIR overrides must name that exact child and it must sit outside this source
tree. See [DATA.md](../DATA.md) for selector precedence and switching. Final outputs,
their exact lock and generated partial paths are resolved inside that directory before
device work and again before atomic promotion. These checks are path-only: no Git or
GitHub call runs at write time, and keeping DATA out of public repositories is enforced
by the commit and push hooks. DATA paths, ancestors, locks and SQLite sidecars cannot
contain a `.git` component or be symlinks, reparse points or multiply linked files.

## Commands and device selection

Run from the canonical tool repository root. Commands use paths relative to the private data
home. The account 10000 below is generated synthetic data, not an actual account.

```bash
python tools/qq_doctor.py
python tools/qq_pull.py --uin 10000 --out qq_db_pull/candidate.db
python tools/qq_keyfind.py --db qq_db_pull/candidate.db --owner 10000 --out qq_keys/recovery.json
python tools/qq_decode.py --db qq_db_pull/candidate.db --evidence qq_keys/recovery.json --out qq_json/messages.jsonl
```

Doctor defaults to local dependency and private-storage checks without contacting a device or
writing a probe file. For the authorized export, add `--device --serial <selected-device>` to
check existing root, classic-client version, account files and an exact Frida Python/server
version match. Use `--server-binary` if the device's server executable has a different path.
Readiness does not claim that an actual export was tested.

For multiple devices, add `--serial` to pull. Multiple accounts require `--uin`; discovery never
chooses an arbitrary first account. Root must already be available through adb shell. A snapshot
with an active WAL/journal is rejected. Obtain a stable snapshot yourself before retrying; this
tool does not stop the application to force one.

## Snapshot and recovery

Pull uses a unique `/data/local/tmp/qq-export-<random>.db` staging file, restrictive umask 077
before copying, and mode 600. It checks copy, chmod, pull and removal. Device staging cleanup is
attempted even after a failed transfer; failure names the path and prevents promotion. Existing local candidates are
never treated as the new transfer. The source filename selects an account, but ownership remains
unverified until the obfuscated selfuin/sender fields can be checked after key recovery.

Recovery attaches to an already running QQ client. Open two distinct longer messages that also
exist in the snapshot; do not spawn or patch the app. The default Frida endpoint is loopback port
27044; change `--host` or `--pid` for the selected device. Python/server Frida 16.x must match and
provide Java. `--seconds` is bounded to 1..120. Incomplete scans and ambiguous message identities
fail. The private evidence bundle records key bytes, distinct plaintext observations, exact row
identities, period, database hash and a separate UTF-8 decoding rate.

Decode requires that bundle, never just an unverified key string. It checks complete known pairs,
account fields, schema and the stable database hash. Recovery and decoding each use one frozen
copy beside the private input, read with SQLite immutable mode. All stages reuse the same bytes;
the source hash and live-journal checks run again before promotion. Temporary snapshot cleanup
also completes before export promotion. Valid UTF-8 alone proves nothing about the key.
Every supported text row must decode before the temporary JSONL replaces an old archive.
Whitespace-only text is preserved exactly, and its timestamp is validated like every other row.
NULL/non-numeric message identities fail; signed 64-bit identities are canonicalized and checked
for uniqueness. Output and lock paths cannot alias the database, its WAL/SHM/journal, or evidence.
Empty exports, malformed timestamps, source changes and pre-promotion failures preserve old bytes.

## Interrupted transactions

Transaction locks prevent overlapping writers. A crash may leave a lock or partial file; inspect
what the previous operation completed before deleting it. After replacement, cleanup failure
returns nonzero with `status=committed_cleanup_required`, `committed=true`, the output path and
remaining cleanup paths. The new output already exists. Before replacement, cleanup failure
returns `failed_cleanup_required` with `committed=false`. Do not describe either as a clean run,
or describe a committed output as an unchanged old archive. Real artifacts and evidence are
versioned in the PRIVATE companion. Do not publish examples copied from a real run.

## Evidence limits

The CLI evidence is local and unsigned, not proof supplied by QQ. It cannot authenticate a bundle
forged by someone who can modify both the database and evidence. Real Android/QQ/Frida compatibility and archive completeness require their own
measured evidence.
