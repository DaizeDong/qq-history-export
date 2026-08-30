# qq-history-export

Export the local chat history of the classic mobile QQ client off a rooted Android device or emulator into organized JSON, decoding the on-device obfuscation with a key it recovers from the running app.

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Powered by Frida](https://img.shields.io/badge/Powered%20by-Frida%2016.x-green?style=flat)](https://frida.re)
[![Client](https://img.shields.io/badge/Target-com.tencent.mobileqq%208.x-purple?style=flat)](docs/REVERSE_ENGINEERING.md)

---

## ⭐ Read this first, the design philosophy

The database is not encrypted, and that is the trap. The classic mobile QQ client (`com.tencent.mobileqq`, the 8.x line before QQ NT) stores its history in a plain SQLite file you can open with any reader. What is obfuscated is smaller and easier to miss: the message payload and the account number columns are each XOR'd with one short repeating key. So the naive approach, pull the file and read it, gets you a valid database full of scrambled bytes, and the naive fix, guess a few-byte key from the first characters that decode cleanly, gets you messages that are correct for the first few characters and garbage after. The key period is fifteen bytes in practice, and a shorter prefix that looks right is the single most expensive way to be wrong here.

The value of this tool is that it does not guess. It recovers the whole repeating key from ground truth by reading the client's own decoded messages out of memory while QQ is running, matches each plaintext message to its encrypted row in the database, and reads the key straight off the aligned plaintext/ciphertext pair. After that one online step everything is offline: open the file, XOR with the recovered key, classify, write JSON.

It is also **private by construction**. The one output of this tool is a person's entire QQ history, verbatim, including one-on-one messages. The pulled database and every decoded message are treated as private data that physically cannot land in this repository. See the data boundary note below. That constraint is not a courtesy, it is enforced.

## What it is (and isn't)

**It is** a one-shot local export: point it at a rooted device where you are logged into your own QQ, get back one JSON object per text message, organized per conversation, decoded and readable.

**It isn't** a network scraper, a way to read accounts you are not logged into, or a tool for QQ NT. QQ NT uses a different, SQLCipher based store (`nt_msg.db`) and is out of scope. This tool reads only the local database of the account already signed in on the device in front of you, once.

## Requirements

- A rooted Android device or emulator with the classic QQ client installed and signed in. On MEmu the setup already had root plus `frida-server-16` (16.7.19) running.
- `adb` on your PATH, with the device reachable (`adb devices` lists it).
- Python with the `frida` package pinned to **16.x**. This is not optional, see the note at the end.
- `frida-server` **16.x** running on the device, listening on the port you pass to the keyfind step.
- QQ actually running and open to a conversation when you run the keyfind step, since that step reads decoded messages out of the live Java heap.

## Quickstart

The pipeline is three tools, run in order. Give every one a path **outside this repository** for its output, because the database and the decoded messages are private data and the tools refuse to write inside the repo. The synthetic values below (owner `123456789`, friend `10001`, group `20001`) are placeholders; substitute your own real paths.

**1. Pull the database (read only).** This copies `/data/data/com.tencent.mobileqq/databases/<uin>.db` off the device and prints the owner account it belongs to. It uses plain `adb shell`, not `su -c`, because `su -c` can hang; on an emulator `adb shell` is already root.

```bash
python tools/qq_pull.py \
  --serial 127.0.0.1:21503 \
  --out ~/qq-export-work/123456789.db
```

Pass `--uin <n>` only if the device holds several account databases and you want a specific one; otherwise it finds the owner for you.

**2. Recover the key from the running client.** This attaches Frida to the live QQ process, reads decoded messages out of the Java heap (every `com.tencent.mobileqq.data.MessageFor*` instance carries the plaintext in its `msg` field plus a `uniseq`), matches each `uniseq` to the encrypted row in the pulled database, and XORs the aligned plaintext/ciphertext pair to read the repeating key directly. It prints something like `recovered key: <key> (period 15, coverage 98%)`. Copy that key into the next step.

```bash
python tools/qq_keyfind.py \
  --db ~/qq-export-work/123456789.db \
  --host 127.0.0.1:27044 \
  --seconds 20
```

`--host` is where `frida-server` is listening on the device. Use `--pid <n>` to target a specific QQ process, and raise `--seconds` if coverage comes back low because too few conversations were open in memory during the read.

**3. Decode the whole database offline.** No device needed from here. This opens the plain SQLite file, decodes `msgData` and the account columns with the recovered key, classifies each row, and writes one JSON object per text message. It refuses to write anywhere inside the repo, and it aborts rather than write a partial export if the key covers under 90% of messages.

```bash
python tools/qq_decode.py \
  --db ~/qq-export-work/123456789.db \
  --key SYNTHKEY01234AB \
  --owner 123456789 \
  --out ~/qq-export-work/messages.jsonl
```

If step 3 aborts on coverage, go back to step 2 with QQ open to more conversations and a longer `--seconds`, so the heap read sees more plaintext to anchor the key against.

## How it works

The short version is above: plain SQLite, one short repeating XOR key over the payload and account columns, key recovered per run from the live client rather than hardcoded. A text message has `msgtype` `-1000` and its content in `msgData`; conversations are one table each, named `mr_friend_<uppercase md5 of the friend account>_New` for private chats and `mr_troop_<uppercase md5 of the group>_New` for groups. The full account of the table layout, the exact columns, the fifteen byte key period and why a shorter prefix decodes only the first few characters, and how the heap read anchors the key, is in **[docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md)**. Read it there; it is not repeated here.

To exercise the whole pipeline with zero real data, `tools/make_fixtures.py` builds a synthetic database (fake accounts `10000` and `10001`, synthetic key `SYNTHKEY01234AB`, obviously fake message text) and `tools/test_qq.py` round trips against it.

## Data boundary

The pulled database and every decoded message are **DATA**: they are the real, verbatim chat history of a real person, and they never enter this repository. This is declared in `.dataclass.json` and enforced by a build gate. The landing directories the pipeline writes to are sealed, so a real run cannot deposit history at a repo-relative path even with `git add -f`. Real-run output belongs in the private companion config (`~/.qq-history-export-config/data/`, overridable with `$QQ_HISTORY_EXPORT_DATA_DIR`), resolved at runtime by `tools/datadir.py`, never back in the repo.

The rule for every example, doc, test, and commit is that only synthetic values ever appear: account `123456789` or `10000`, friend `10001`, group `20001`, and invented, obviously fake message text. Never write a real account number, a real message, or any real personal detail anywhere in this repository. If you need an example, make one up.

## The Frida 16 requirement

Pin `frida` (and `frida-server` on the device) to the **16.x** line. Frida 17 removed the built in Java bridge, and the key recovery in step 2 depends on that bridge to walk the Java heap and read the `MessageFor*` instances that carry the plaintext. On Frida 17 the heap read simply cannot work, so the key is never recovered and the offline decode has nothing to run on. This is a hard version floor, not a preference.

## License

[MIT](LICENSE).
