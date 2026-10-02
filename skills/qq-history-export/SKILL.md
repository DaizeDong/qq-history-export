---
name: qq-history-export
description: Export your classic mobile QQ text history from rooted Android with verified key evidence and private JSONL. Use for 导出 QQ 聊天记录 or archive QQ chat.
---

# QQ History Export

Use for the user's own account on classic mobile QQ, before NT. The supported schema is
plain SQLite with XOR-obfuscated fields. Other clients and QQ NT are unsupported.

## Start with one request

Resolve this skill's canonical source, then use repository-root `tools/` paths even from an
installed alias or unrelated working directory. Reuse the selected private companion, device
and account. Ask one combined question only for missing storage, ambiguous devices/accounts,
or an unclear export scope. An explicit export request permits its necessary device reads;
a maintenance or review request alone does not.

Load `../../docs/WORKFLOW.md` for exact commands and failure recovery. Load
`../../docs/REVERSE_ENGINEERING.md` only for schema or cipher details.

## Required boundaries

- Runtime databases, keys, known plaintext and output are DATA in a verified PRIVATE versioned
  companion. Set `QQ_HISTORY_EXPORT_CONFIG` or `QQ_HISTORY_EXPORT_DATA_DIR`. The CLI rejects
  unknown/public/unversioned destinations and has no tool-repository fallback.
- Use only an already rooted device with the classic client. Do not install root, patch QQ,
  spawn through Frida or stop applications as part of diagnosis.
- The bundled heap agent requires the Frida 16.x Java bridge on both sides. A missing bridge
  or incomplete heap scan is a failure, not partial recovery.
- Short readable prefixes and UTF-8 coverage cannot validate a key. Require two distinct exact
  known plaintext rows, each spanning at least two complete periods, plus matching account fields.
  Never assume a fixed period from an earlier installation.

## Pipeline

Run `tools/qq_doctor.py` for local readiness. Add `--device` only within an authorized export
to verify existing root and client/Frida versions; this does not attach to the application.

1. `tools/qq_pull.py`: choose the account, check bounded adb calls, reject active SQLite journals,
   compare stable hashes, validate SQLite and clean the unique staging file. The output must be
   new. Report `pulled_candidate`, with ownership still unverified because the account fields
   have not been decoded. This creates temporary device files; it does not modify the source DB.
2. `tools/qq_keyfind.py`: attach to the already running client, require a completed heap scan,
   match unique message identities, validate independent plaintext evidence and account fields,
   and save a private recovery bundle bound to the database hash. Never print the key.
3. `tools/qq_decode.py`: validate the bundle, require complete UTF-8 coverage and decoded account
   agreement against one frozen private copy, write the whole export to a temporary file, then
   replace the destination atomically. Source changes or new journals reject promotion. Numeric
   message identities must be unique. Inputs and SQLite sidecars are reserved against output aliases.
   Validation and pre-promotion write failures preserve existing archives.

After interruption, inspect the existing candidates and any transaction lock. Do not delete a
lock blindly or overwrite an earlier raw candidate. Reuse a recovery bundle only when its full
DB hash still matches. Cleanup failure names the remaining staging file and requires review.
For local `committed_cleanup_required` receipts, the new output already exists; inspect the
listed cleanup paths before retrying. `failed_cleanup_required` means replacement did not occur.

## Delivery

Return the private artifact path, counts, database hash, owner-verification status and decoding
coverage separately. State that only supported text rows were exported. A recovery bundle is
an unsigned local observation record; forged or externally supplied bundles need provenance
review. Do not claim whole-account completeness or universal device compatibility.

## Offline tests

Run `python -m pytest tools -q` and `python tools/test_qq.py` from the canonical repository root.
Fixtures come from `tools/make_fixtures.py`; device/Frida regression calls are intercepted.
Synthetic passing tests do not constitute a live-device export.
