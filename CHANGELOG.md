# Changelog

All notable changes to this project are documented here (Keep a Changelog style).

## [Unreleased]

### Removed
- The `guards` and `style` submodules and the `pii-guard`, `dash-guard`, `doc-contract`, `load-budget` and `fleet-sync` workflows. The `.githooks` shims run the local fleet-guards and fleet-style checkouts named by `git config fleet.guards` and `fleet.style` and block when either is unset. `qq_storage` resolves the companion through `fleet_guards.runtime.companion_resolver` (`pip install -e "$(git config --get fleet.guards)"`).
- The test suite (`tools/test_*.py`), the fixture generator `tools/make_fixtures.py` and the `offline-tests` CI workflow. Commit and push privacy gates are unchanged.
- Runtime PRIVATE proof. `qq_storage.private_path()` no longer runs `git config`/`remote`/`rev-parse`, the `gh` visibility query, the Guards TLS trust proof or `storage_contract.authorize_artifact_write` admission, and the routing-environment refusal that only protected those calls is gone. Destinations are now checked by path only: an existing companion `data/` directory outside this source tree, results inside it, no `.git` component, link or multiply linked file. A missing companion still fails before device access with init guidance; no in-repo fallback. The `artifact_id` argument is removed from callers. `qq_doctor` no longer requires `gh`. Proof-only tests (`test_review_round3.py`, `test_visibility_any_gh_account.py`, route/TLS/admission cases) and their fixture generators are deleted; the remaining storage tests assert path-only behaviour. Commit and push gates are unchanged.

### Fixed
- The live PRIVATE visibility check no longer depends on which gh account is active: it asks through the pinned guards kit's `query_github_visibility`, which tries the owner's stored account, every other stored account, then gh's default, and never switches the active account. Before, an active account that could not see the companion made every proof fail closed. Only PRIVATE is accepted.

### Changed
- `qq_storage` loads `guards/tools/datadir.py` and resolves the companion `data/` directory once per process for each tool root and selector values, instead of on every `private_path` call. `write_bundle` and `qq_decode.export_database` drop their own "destination changed" recheck; `atomic_output` still rechecks before promotion and `qq_pull` keeps its recheck across the device copy.
- `qq_doctor` no longer lists `git` as a readiness requirement; no runtime tool runs it. The plugin description, ROADMAP and the `qq_decode --out` help say "private companion" instead of "verified private companion".
- Bind concrete runtime writer destinations and transaction files to canonical source artifact admission before creation. Offline regression controls preserve PRIVATE, retention, topology and versioning refusals.
- Set a 64 MiB companion working-data review threshold. Required observations and
  recovery state stay protected when the threshold is exceeded.
- Require database-bound key and account evidence for export, with independent known plaintext observations and variable-period XOR recovery.
- Freeze the database snapshot used for validation and export; reject journal activity, invalid identities and incomplete selected-text decoding before replacement.
- Verify a PRIVATE versioned destination before writing databases, recovery evidence or JSONL output.
- Return distinct cleanup-required receipts when replacement has already committed, so callers can inspect before retrying.
- Clarify the recovery tradeoffs and the separate scope of synthetic checks and real-device acceptance.

### Fixed
- Accept standard Git TLS backends and use canonical Guards proof for the selected Git installation's bundled CA, while rejecting custom trust overrides.
- Reject selected companions without data/ and alternate DATA roots before device access. Bind final output paths to their source artifact and shared PRIVATE, versioned write admission; document storage-only discovery and switching.
- Accept pager settings while isolating Git and GitHub subprocess environments used for private storage verification.

## [0.1.0] - 2026-08-30

### Added
- Initial release: local chat history export for the classic mobile QQ client (com.tencent.mobileqq, the 8.x line before QQ NT). Read-only `adb pull` of the per account SQLite message database, frida 16 key bootstrap that recovers the repeating XOR key from the running client's Java heap, fully offline XOR decode into one JSON object per text message, synthetic fixtures plus a round trip test that touch zero real data, and data boundary gates that keep every pulled database and decoded message out of the repository.
