# How classic mobile QQ stores chat history

This note records what the export path relies on. It covers the classic mobile QQ client
(`com.tencent.mobileqq`, the 8.x line that predates QQ NT). QQ NT uses a different, SQLCipher based
store (`nt_msg.db`) and is out of scope here.

Every worked example below uses the synthetic account `123456789`. No real account number appears in
this repository.

## The database is plain SQLite, the fields are obfuscated

Invariant: the file is a normal unencrypted SQLite 3 database. Only the message payload columns and
the account number columns are obfuscated. You can open the file with any SQLite reader and list the
tables without a key.

Path on a rooted device:

```
/data/data/com.tencent.mobileqq/databases/<uin>.db
```

where `<uin>` is the owner account number, for example `123456789.db`. The first sixteen bytes of
the file are the literal ASCII `SQLite format 3\0`, which confirms there is no whole file
encryption.

## Table layout

Invariant: one table per conversation, named by the md5 of the peer identifier.

Private chats are `mr_friend_<MD5>_New`, where `<MD5>` is the uppercase hex md5 of the friend
account number. Group chats are `mr_troop_<MD5>_New`, where `<MD5>` is the uppercase hex md5 of the
group number. The mapping is verifiable: for the owner `123456789`, the uppercased md5 of the string
`123456789` names the owner's own self chat table, and the same rule holds for every friend and
group.

Relevant columns on a message table: `msgtype` is the message kind, and `-1000` is a plain text
message. `msgData` is the payload, obfuscated. `senderuin`, `selfuin`, and `frienduin` are account
numbers, obfuscated the same way. `issend` is the direction, `2` means the owner sent it and `1`
means received. `time` is a unix timestamp stored in the clear. `uniseq` is the message identity,
stored in the clear, and it is the join key that makes the key recovery below work.

## The field cipher is a repeating XOR key

Invariant: obfuscation is a byte wise XOR against a short key repeated to the length of the field.
Decoding is the same operation as encoding, XOR the same key again. The key is global for the
database: it depends only on the byte offset inside the field, not on the row, the table, or the
sender. The proof is that one identical short message produces byte identical `msgData` in two
different tables.

The one thing you must get right is the period. On the reference device the key is fifteen bytes of
ASCII digits. An earlier pass mistook the first nine of those bytes for the whole key, which
happened to decode the first three Chinese characters of every message (nine bytes is exactly three
UTF-8 characters) and then diverged into garbage. That looked like a per message keystream and sent
the analysis down a blind alley. It was simply the wrong period. Once the period is fifteen, the
same key decodes every message in the database to the end, at full coverage.

## Recovering the key is easy from the running client, hard from the database alone

You can read the first nine key bytes straight out of any owner sent row: `senderuin` there is the
owner account number, which is known plaintext, so XOR the stored bytes against the ASCII digits of
the account number. That gives nine bytes, which is not the whole fifteen, and trying to extend the
key by voting on UTF-8 validity across many messages is unreliable in practice.

The running client hands you the rest for free. When QQ loads a message it builds an in memory
`com.tencent.mobileqq.data.MessageFor*` object whose `msg` field holds the already decoded text and
whose `uniseq` field holds the same message identity that keys the encrypted row on disk. So the
recovery is: attach to the running client, walk the Java heap for `MessageFor*` instances, read
their `msg` and `uniseq`, and for one message that is at least as long as the period, look up the
encrypted `msgData` for that `uniseq` in the database. XOR the aligned plaintext and ciphertext and
the repeating key falls straight out. One long message is enough, and a second one cross checks it:
two independently recovered keys agree byte for byte. This is exactly what `tools/qq_keyfind.py`
does. It does not call any decrypt routine inside the client; it only reads plaintext the client
already decoded and lets the XOR give up the key.

After the key is recovered once, the whole database decodes offline with `tools/qq_decode.py`. The
recovery reads the client's heap but never writes to it and never patches it.

A note on frida versions: the heap read needs the frida Java bridge, and frida 17 removed that
bridge from the injected agent, so `Java` is undefined there and the read cannot work. Use frida
16.x on both sides. The MEmu device already shipped a `frida-server-16` binary for this reason.

## What is data and what is not

The pulled database and every decoded message are real run output. They are private data and never
enter this repository, which is enforced by `.dataclass.json` and the repo relative write refusal in
the tools. Tests run against a synthetic database produced by `tools/make_fixtures.py`, which
encrypts fake messages with a synthetic key so the round trip can be checked without touching any
real account.
