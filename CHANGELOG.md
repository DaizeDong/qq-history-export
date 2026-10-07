# Changelog

All notable changes to this project are documented here (Keep a Changelog style).

## [Unreleased]

### Storage review threshold
- Set a 64 MiB companion working-data review threshold. Required observations and
  recovery state stay protected when the threshold is exceeded.

### Changed
- Require database-bound key and account evidence for export, with independent known plaintext observations and variable-period XOR recovery.
- Freeze the database snapshot used for validation and export; reject journal activity, invalid identities and incomplete selected-text decoding before replacement.
- Verify a PRIVATE versioned destination before writing databases, recovery evidence or JSONL output.
- Return distinct cleanup-required receipts when replacement has already committed, so callers can inspect before retrying.
- Clarify the recovery tradeoffs and the separate scope of synthetic checks and real-device acceptance.

### Fixed
- Accept pager settings while isolating Git and GitHub subprocess environments used for private storage verification.

## [0.1.0] - 2026-08-30

### Added
- Initial release: local chat history export for the classic mobile QQ client (com.tencent.mobileqq, the 8.x line before QQ NT). Read-only `adb pull` of the per account SQLite message database, frida 16 key bootstrap that recovers the repeating XOR key from the running client's Java heap, fully offline XOR decode into one JSON object per text message, synthetic fixtures plus a round trip test that touch zero real data, and data boundary gates that keep every pulled database and decoded message out of the repository.
