---
name: qq-history-export
description: "Use to export the local chat history of the classic mobile QQ client (com.tencent.mobileqq, the pre-NT 8.x line) off a rooted Android device or emulator into organized JSON. Triggers: export qq history, archive qq chat, 导出 qq 聊天记录, 拉 qq 消息数据库."
---

# QQ History Export

> **Caveat (data)**: The single output of this skill is a person's entire QQ chat history in the clear, one-on-one messages included. The pulled database and every decoded message are DATA. They never enter this repository. They live under the private data home (default `~/.qq-history-export-config/data/`, override with `$QQ_HISTORY_EXPORT_DATA_DIR`). Every tool that writes refuses a repo-relative output path; do not fight that refusal, point it outside the repo.
> **Caveat (scope)**: This is the classic client only (`com.tencent.mobileqq`, 8.x). QQ NT uses a different SQLCipher store (`nt_msg.db`) and is out of scope. If the pulled file does not start with the ASCII bytes `SQLite format 3`, you are looking at NT and this skill does not apply.

## When To Use

- User has a rooted device or emulator with classic QQ installed and logged in, and wants a local JSON copy of their chat history.
- User wants a grep-able, analyzable dataset of their own private and group messages.

## When NOT To Use

- Target is **QQ NT** (the current desktop or newer mobile build). Different database, different encryption. Not this skill.
- Device is **not rooted**. The database sits under `/data/data/`, unreadable without root. There is no non-root path here.
- User wants **someone else's** messages. This exports the account logged in on the device, nothing more.

## Prerequisites

Confirm every row before touching the pipeline. A miss here shows up as a confusing failure three steps later.

| Check | How | Required |
|---|---|---|
| Rooted device or emulator | `adb shell id` shows uid 0, or `adb root` succeeds | yes |
| adb reachable | `adb devices` lists the serial | yes |
| Classic QQ installed and logged in | a `<uin>.db` exists under the databases dir (Step 1 confirms) | yes |
| Python with frida **16.x** | `python -c "import frida; print(frida.__version__)"` starts with `16.` | yes |
| frida-server **16.x** running on the device | `adb shell ps -A | grep frida-server`, or the port responds | yes |
| Python 3 | `python --version` | yes |

The frida version is not a soft preference. Frida 17 removed the built in Java bridge from the injected agent, so the heap read in Step 3 sees `Java` undefined and the whole key recovery is impossible. Both the Python side and the on device `frida-server` must be on the 16.x line. On MEmu the device shipped `frida-server-16` (16.7.19) for exactly this reason.

## Critical Rules (Non-Negotiable)

1. **Decoded output is DATA and goes outside the repo.** Both `qq_pull.py` and `qq_decode.py` refuse a `--out` inside this repository and exit non-zero. Write the pulled database and the decoded JSONL under `~/.qq-history-export-config/data/` (or `$QQ_HISTORY_EXPORT_DATA_DIR`). Never paste a real account number, a real message, or any real personal detail into a doc, an example, a commit, or this conversation's persistent notes.
2. **The key has a fifteen byte period. Do not accept a shorter one.** An earlier analysis mistook the first nine bytes for the whole key, which decoded the first three Chinese characters of every message and then produced garbage. The recovery tool detects the true period from one known plaintext pair; you validate it by coverage (see Step 3). A key that covers well under 100% is a wrong or truncated key, not a partial success.
3. **On an emulator, `adb shell` is already root. Do not wrap commands in `su -c`.** `su -c` can hang the shell with no output. The pull tool uses plain `adb shell` on purpose; keep it that way.
4. **Do not use frida spawn on the emulator.** Spawn-and-attach is flaky here and can leave QQ in a state with nothing decoded on the heap. Start the app normally (`adb shell am start ...` or just tap it), let a chat load so messages are decoded in memory, then attach by name or pid. The heap read only works against an already running, already used client.

## Workflow

The pipeline is three tools in order: pull the database, recover the key from the running client, then decode offline. Everything after Step 2 is offline and touches nothing on the device.

### Step 1: Pull the database

```bash
python tools/qq_pull.py \
  --serial 127.0.0.1:21503 \
  --out ~/.qq-history-export-config/data/qq_db_pull/pulled.db
```

Omit `--serial` if only one device is attached. If several accounts have logged in on the device, the tool lists them and you pass the one you want with `--uin`.

**Check:** the tool prints the owner uin (the database file name is the account number). Note that uin; `qq_decode` needs it as `--owner`. If it prints "no `<uin>.db` found", the device is not rooted, QQ is not installed, or no account is logged in. Fix that before continuing.

### Step 2: Make sure QQ is running and has decoded some messages

Start QQ on the device the normal way and open a conversation so its messages load into memory. A longer conversation is better: the key recovery pins the fifteen byte period off the longest known plaintext it can find, and a chat of only very short messages may not span two full periods. Do not spawn QQ through frida (Critical Rule 4).

### Step 3: Recover the field key from the running client

```bash
python tools/qq_keyfind.py \
  --db ~/.qq-history-export-config/data/qq_db_pull/pulled.db \
  --host 127.0.0.1:27044 \
  --seconds 20
```

This attaches with frida, walks the Java heap for `com.tencent.mobileqq.data.MessageFor*` instances (each carries the decoded text in its `msg` field plus a `uniseq`), matches each `uniseq` to the encrypted row in the pulled database, and reads the repeating key straight off the aligned plaintext, ciphertext pair. Pass `--pid` if you want to target a specific process instead of resolving `com.tencent.mobileqq` by name; raise `--seconds` if the heap scan does not finish.

**Check:** it prints `recovered key: <key>  (period N, coverage M%)`. You want period 15 and coverage at or near 100%. The tool itself refuses to print a key whose coverage is under 90% and tells you to load a longer chat and retry. If you see the fatal message about a missing Java bridge, you are on frida 17 somewhere; fix the version (Prerequisites) and rerun. If it reports no uniseq overlap, the running client and the pulled database are for different accounts, or the loaded chat is not stored locally; open a chat that exists in the pulled database.

Copy the printed key for the next step. The key is ASCII digits in practice.

### Step 4: Decode the whole database offline

```bash
python tools/qq_decode.py \
  --db ~/.qq-history-export-config/data/qq_db_pull/pulled.db \
  --key <key from Step 3> \
  --owner <owner uin from Step 1> \
  --out ~/.qq-history-export-config/data/qq_json/messages.jsonl
```

This opens the plain SQLite database, walks every `mr_friend_*` and `mr_troop_*` table, decodes `msgData` and the account columns with the key, keeps the text messages (`msgtype -1000`), and writes one JSON object per message. It never writes back to the source and never touches the network. It re-checks coverage and aborts if under 90%, so a wrong key cannot silently produce junk.

**Check:** it prints `decoded N text messages (X yours, Y others) at M% key coverage -> <path>`. Coverage should match Step 3, at or near 100%. If it refuses because the `--out` is inside the repo, move the path under the data home. Each record has `text`, `is_me`, `ctx` (`dm` or `group`), `ts`, `sender`, `conv`, and `uniseq`.

## The Cipher

The database is a plain SQLite file; only `msgData` and the account number columns are obfuscated, each byte XORed against a fifteen byte repeating key that is the same across every row and table. Tables are named `mr_friend_<uppercase md5 of the friend account>_New` and `mr_troop_<uppercase md5 of the group>_New`; a text message is `msgtype -1000` with its content in `msgData`. The full derivation, why the period matters, and how the key is recovered from one known plaintext pair rather than guessed, is written out in `docs/REVERSE_ENGINEERING.md`. Read that; this skill does not restate it.

## Pitfalls (Reference)

- **Frida 17 has no Java bridge.** The injected agent sees `Java` undefined, so the heap read in Step 3 cannot run. Pin frida to 16.x on both the Python side and the on device `frida-server`. This is the single most common failure.
- **Spawn on the emulator misbehaves.** Start QQ normally and attach; do not `frida -f` spawn it. The heap must already hold decoded messages, which only happens after a chat has loaded in a running client.
- **`su -c` hangs.** On the emulator `adb shell` is already root. Wrapping in `su -c` can hang with no output. The pull tool avoids it; you should too.
- **The fifteen byte period.** A nine byte prefix decodes the first three Chinese characters of a message and then diverges into garbage. Trust the coverage number, not the first few readable characters. Anything short of near total coverage is a wrong key.

## Testing With No Real Data

`tools/make_fixtures.py` builds a synthetic database (owner `10000`, friends `10001` and `10002`, group `20001`, synthetic key `SYNTHKEY01234AB`, obviously fake text) and `tools/test_qq.py` round trips the decoder against it, including a poison case with a wrong key that asserts coverage collapses. Run `python tools/test_qq.py` to exercise the whole decode path without any device and without any real account. When you need an example anywhere, use those synthetic values or account `123456789`; never a real one.

## Output

A single JSONL file under the data home, one JSON object per text message:

```
~/.qq-history-export-config/data/
├── qq_db_pull/pulled.db        ← the pulled SQLite database (DATA)
└── qq_json/messages.jsonl      ← decoded messages, one per line (DATA)
```

Both paths are real run output and stay outside this repository, always. The repository ships only code, docs, and the synthetic fixture.
