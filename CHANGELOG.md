# Changelog

All notable changes to this project are documented here (Keep a Changelog style).

## [0.1.0] - 2026-08-30

### Added
- Initial release: local chat history export for the classic mobile QQ client (com.tencent.mobileqq, the 8.x line before QQ NT). Read-only `adb pull` of the per account SQLite message database, frida 16 key bootstrap that recovers the repeating XOR key from the running client's Java heap, fully offline XOR decode into one JSON object per text message, synthetic fixtures plus a round trip test that touch zero real data, and data boundary gates that keep every pulled database and decoded message out of the repository.
