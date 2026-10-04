# qq-history-export, Design Philosophy

## Recovery needs evidence independent of decoding coverage

An incorrect repeating XOR key can still yield valid UTF-8. The exporter requires distinct known
plaintext observations spanning the key period, verifies the decoded owner and sender fields,
and binds that evidence to the selected database. A coverage percentage describes the selected
text fields; it cannot establish key correctness or whole-account history completeness.

This deliberately limits export to the supported classic mobile QQ schema and a client that can
provide the required observations. Missing evidence produces a refusal instead of a plausible archive.

## Validation and replacement use the same snapshot

Recovery and decoding freeze a standalone private database copy. Source changes, journal activity,
invalid message identities or incomplete decoding prevent promotion. Atomic replacement preserves
the previous archive until the new one has passed validation. A cleanup failure after replacement
has a distinct committed receipt, so the caller can inspect the artifact before retrying.

## The archive has a private versioned home

The source database and recovery bundle contain private chat data, including known plaintext.
Writing commands verify a separate PRIVATE companion before acting. This creates a durable history
without an in-repository fallback that could publish a real export with the tool.
The evidence bundle remains a local observation record, not an attestation signed by QQ.

## Offline checks have a defined scope

Generated synthetic databases exercise recovery, decoding and preservation contracts without
an account or phone. They do not establish live Frida compatibility, device behavior or account
history completeness. Those properties require separate authorized acceptance on the selected device.
