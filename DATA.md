# Private export storage

[storage.contract.json](storage.contract.json) declares the companion layout and
retention conditions. The existing [workflow](docs/WORKFLOW.md), database checks,
and evidence validator remain authoritative for content and verification.

Paths in the contract are relative to a separate PRIVATE companion root. Set
`QQ_HISTORY_EXPORT_CONFIG` to that existing clone, or `QQ_HISTORY_EXPORT_DATA_DIR`
to its `data` directory. An uninitialized tool fails before device access or
writing. Installing the tool does not require creating an empty companion.

| Companion path | Required purpose |
| --- | --- |
| `data/qq_db_pull/*.db` | Stable candidates still needed by recovery or selected export verification. |
| `data/qq_keys/*.json` | Key and account evidence bound to the matching database hash. |
| `data/qq_json/*.jsonl` | Selected verified text exports and their current downstream inputs. |

The documented flat directories keep final files distinct from temporary
`.qq-snapshot-*` copies, `.partial` files, and transaction locks. CLI relative paths
are relative to the private `data` directory. Other filenames or directory layouts
need an explicit contract entry before use. Output entrypoints bind the final file
to its declared database, evidence or export artifact and use shared write admission
before access and again before promotion. This requires committed PRIVATE storage,
a fresh local Guards visibility receipt and a final path that Git does not ignore.
Read-only input resolution remains separate from output admission. Legacy
`qq_export` or `qq_organized` directories have no current producer or consumer here
and need individual review before retention or removal.

Keep the database and evidence while an active recovery, verification, or promised
rebuild depends on them. Keep the selected final export while it is requested or
referenced. Older attempts and duplicate exports need no permanent archive once
their useful result is preserved and their dependencies have ended. Version the
required real artifacts only in the PRIVATE companion.

Normal transactions remove their staging files. A crash requires checking the
writer and the `committed` receipt before cleanup. Locks and SQLite sidecars are
protected from generic retirement. Storage contracts do not schedule deletion or
rewrite Git history.

Use the shared `storage_contract.py` from skill-smith for `validate`, `check`,
`plan`, and `apply`; do not copy that checker into this repository. `validate`
checks this contract without opening a companion. Inventory and retirement require
an initialized PRIVATE companion and an explicitly reviewed plan.

Storage-only discovery uses `QQ_HISTORY_EXPORT_DATA_DIR` first, then
`QQ_HISTORY_EXPORT_CONFIG`, then its `QQ_HISTORY_EXPORT_CONFIG_DIR` alias, followed by
[Guards companion discovery](guards/COMPANION.md) for proven siblings and home defaults
(`~/.qq-history-export-config` and `~/.qq-history-export-data`). All accepted layouts
must resolve to the companion root plus `data/`. A selected CONFIG without that child
is uninitialized and fails before device access or output creation. Clear an inherited
DATA_DIR before switching CONFIG. No settings registry or empty companion is required.

The atomic output writer admits the exact lock and generated partial filename through their source artifact IDs before creating either file or its parent directory. These declarations remain versioned, so effective ignore rules refuse them. The partial file is created exclusively only after admission and checked again before promotion. This check complements the concrete database, evidence and JSONL destination admission; it does not establish a successful live device recovery.
