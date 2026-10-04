# qq-history-export

Export your classic mobile QQ text history with a verified database snapshot, independent key evidence and an atomic JSONL export.

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#languages)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.0-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

## Design Philosophy

A readable SQLite file does not establish that its message fields decode correctly. Short XOR
keys can produce valid UTF-8 that is still wrong. This exporter therefore requires independent
known plaintext messages, binds the recovered key to a frozen database snapshot, and verifies
the decoded account fields before replacing an archive. Decoding coverage remains a separate measurement.

This choice requires observation of a supported running client and refuses exports when the
evidence is incomplete. It preserves the previous archive when transfer or validation fails.
Databases, recovery evidence and decoded messages stay in a verified PRIVATE versioned companion,
so an export can be retained and compared without placing chat history in the public tool.
Synthetic checks establish the local contracts; device compatibility and whole-account completeness
still need their own evidence.

[Read the full design philosophy](PHILOSOPHY.md).

## Scope and requirements

Classic mobile QQ (`com.tencent.mobileqq`, pre-NT 8.x) is supported by the documented schema. QQ NT and other schemas are rejected. The workflow needs an already rooted Android device or emulator, adb, a running QQ client, and matching Frida 16.x Python/server installations with the Java bridge. It does not install root or start/stop the application. Live compatibility must be checked on the selected device.

Python 3.11 or newer, Git and authenticated `gh` are required. The device must provide `sha256sum`. A live SQLite WAL or rollback journal blocks raw copying; obtain a stable snapshot before retrying.

## Install

```bash
git clone --recurse-submodules https://github.com/DaizeDong/qq-history-export.git
```

Load `skills/qq-history-export/SKILL.md` from the canonical clone. Run the commands below from its repository root.

## Config

Point `QQ_HISTORY_EXPORT_CONFIG` at a separately cloned PRIVATE companion with an existing `data/` directory. `QQ_HISTORY_EXPORT_DATA_DIR` can select its existing data directory directly. The pinned guard resolves the location; Git and `gh` verify the actual destination repository. Public, unknown and unversioned destinations fail. Real records are committed in the private companion; credentials remain outside Git.

## Quickstart

Say "Export my classic QQ history." The skill resolves saved storage and device selection, then asks once for any missing account or device. Existing authorization governs device access; unrelated repairs do not authorize an export. Detailed commands and recovery states are in [the workflow](docs/WORKFLOW.md).

All output paths below are relative to the configured private data directory. The account value is synthetic; use the account selected during your run.

```bash
python tools/qq_pull.py --uin 10000 --out qq_db_pull/candidate.db
python tools/qq_keyfind.py --db qq_db_pull/candidate.db --owner 10000 --out qq_keys/recovery.json
python tools/qq_decode.py --db qq_db_pull/candidate.db --evidence qq_keys/recovery.json --out qq_json/messages.jsonl
```

The pull requires a new destination. It checks adb statuses, stable source/local hashes and SQLite integrity, cleans its unique device staging file, and returns a candidate with `owner_verified=false`. Decoded account verification occurs after recovery. No key is printed or copied through command-line arguments.

The recovery bundle contains the key and known plaintext observations. Treat it as private chat data. Recovery and decoding freeze a private standalone copy and reuse its exact bytes for validation, account checks and export. Source changes or new journal activity reject promotion. Message identities must be signed 64-bit integers and unique across supported text rows. The database, SQLite sidecars and recovery evidence are reserved against output and lock aliases.

Invalid evidence, corruption, partial decoding and failures before replacement leave the old archive intact. If replacement succeeded but lock cleanup failed, the CLI exits nonzero with a JSON `committed_cleanup_required` receipt and `committed: true`. The new artifact already exists: inspect the listed cleanup paths before retrying. A `failed_cleanup_required` receipt with `committed: false` means replacement did not occur.

## Output and evidence

Each JSONL text record contains `text`, `is_me`, `ctx`, `ts`, `sender`, `conv` and `uniseq`. Final CLI output reports message counts, owner verification, key-evidence status, database hash and decoding coverage. Attachments and non-text message types are excluded.

The bundle preserves a local observation record; it is not a signed attestation from QQ. Verify its provenance before importing a bundle from elsewhere. A passing synthetic suite does not prove completeness of a real account's history, current device compatibility or key recovery from every client version.

## Offline verification

```bash
python -m pytest tools -q
python tools/test_qq.py
```

All test databases are generated by `tools/make_fixtures.py`. Device and Frida regression calls are intercepted. No real account is needed. [Reverse-engineering notes](docs/REVERSE_ENGINEERING.md) document the schema and obfuscation model.

## Languages

English (`README.md`, authoritative) and 中文 (`README_CN.md`).

## Roadmap and license

[ROADMAP.md](ROADMAP.md) | [CHANGELOG.md](CHANGELOG.md) | [MIT](LICENSE).
