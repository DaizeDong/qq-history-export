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
need an explicit contract entry before use; the CLI currently enforces the private
boundary, while the shared storage checker checks the declared layout. Legacy
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
