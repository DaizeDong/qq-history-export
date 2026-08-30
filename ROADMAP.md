# Roadmap

Current: **v0.1.0**

## v0.1.0 (current)

- Read-only `adb pull` of the classic mobile QQ SQLite database off a rooted device or emulator (`tools/qq_pull.py`)
- frida 16 key bootstrap: attach to the running client, read plain messages out of the Java heap, match uniseq to the encrypted row, and XOR the aligned pair to read the repeating XOR key straight off (`tools/qq_keyfind.py`)
- Offline decode of msgData and the account columns into one JSON object per text message, refusing to write inside the repo and aborting under 90% key coverage (`tools/qq_decode.py`)
- Synthetic fixture database and a round trip test that use no real data (`tools/make_fixtures.py`, `tools/test_qq.py`)
- Data boundary gates: pulled databases and decoded messages are DATA, declared in `.dataclass.json`, and never enter the repository

## Planned

- HTML output alongside JSON, the readable per conversation tree the sister discord tool produces
- Accounts whose key period differs from the fifteen bytes seen in practice, detected and handled rather than assumed
- An offline key recovery path that reads the key from the database alone, so a run no longer needs the client to be running
- Richer message types beyond plain text: images, replies, forwarded cards, and other non text content
