# Stage 246 — independently retained verifier-state continuity checkpoints

Stage 245 atomically stores one-time capture acceptance in a verifier-owned
SQLite database, but restoring an **older copy of that database** can
resurrect already consumed nonces. Stage 246 adds a separate, **read-only**
audit, `tools/audit_record_verifier_checkpoint.py`, to detect regression
relative to a previously captured **independently retained** checkpoint.

This is a bounded **continuity proof against a supplied historical
checkpoint**, not a cryptographic authentication of its origin. The verifier
must maintain the external checkpoint and protect it against rollback by a
different trust domain. The tool cannot do that on its own.

## Design

The checkpoint stores only domain-separated SHA-256 commitments to logical
SQLite records, not the database itself, raw nonces, stream/EXE digests,
addresses, debugger identity, memory words or game data.

Each issued-challenge commitment covers:
- verifier-generated nonce;
- issuance timestamp;
- original expiration timestamp.

Each accepted-capture commitment covers:
- its consumed nonce and original provenance digest;
- acceptance timestamp;
- exactly two accepted raw-stream digests, sorted canonically.

The current DB is opened **read-only** under the existing private file
permission rules. A single SQLite read transaction checks physical integrity,
foreign-key consistency, expected table columns and logical relationships:
issued/accepted/consumed references agree, every accepted capture has exactly
two distinct streams, digest syntax is strict and records are bounded.

The comparison requires the old set of issued commitments and the old set of
accepted commitments to remain subsets of the current logical state. It
therefore allows later issuances and accepted captures **without invalidating
older checkpoints**, but detects deletion or modification of records present
when the trusted checkpoint was made. Replaying a database copy from *before*
that checkpoint will fail if it lacks any recorded item.

No serial numbers, timestamps or checksums can prove that the checkpoint
was really recorded before the current submission. Only a verifier-controlled
independent checkpoint custodian can supply that assurance.

## Local use

Keep the SQLite database under a verifier-owned mode-0700 directory.
Write checkpoints into a **different, private, separately protected**
location; never commit them into a public repository or store the sole copy
next to the database.

### Step 1: Create a private checkpoint after a known good verifier state

```sh
python3 -m tools.audit_record_verifier_checkpoint snapshot \
  /private/verifier/captures.sqlite \
  /independent-private-store/checkpoint-001.json
```

The destination parent directory must be owned by the verifier with no
group/other permissions. The checkpoint file is exclusively created with
mode 0600 and cannot overwrite an existing file. File and parent directory
are fsynced. The command writes the checkpoint privately and prints **only
counts and booleans**, not the commitments.

**Important:** a different path or filesystem alone is not an independent
trust anchor. Copy/retain the checkpoint with an independently protected,
append-only or rollback-resistant custodian. Deleting/replacing the
checkpoint together with the database defeats the comparison. Checkpoint
storage management and authentication are intentionally out of scope.

### Step 2: Verify continuity using the original retained checkpoint

```sh
python3 -m tools.audit_record_verifier_checkpoint verify \
  /private/verifier/captures.sqlite \
  /independent-private-store/checkpoint-001.json
```

- **0:** all previously recorded logical entries still exist unchanged.
- **1:** at least one historical issued/accepted commitment is missing.
  This can reflect rollback or deliberate/accidental database modification,
  not necessarily an attacker.
- **2:** invalid/corrupt database or checkpoint, missing paths, non-private
  database permissions, or invalid histories. Only
  `invalid_private_input` appears in the public JSON error.

The tool accepts checkpoints up to **640 KiB**, covering at most
**4096 issued challenges and 4096 accepted captures**; the database
inspection is likewise bounded. The stage-245 database remains unbounded,
but this optional audit deliberately fails rather than silently truncate
a larger history. Any deployment exceeding these limits requires a newer
checkpoint design, not skipped records.

## Limitations

This is an **offline audit**, not an automatic gate on stage-245 `issue`
or `accept`. A racing writer can commit immediately after the checkpoint
read transaction. For any safety-critical workflow, the verifier must
enforce the external high-water checkpoint inside its operational admission
process before issuing or accepting new sessions and coordinate anchor
updates with DB commits. The current tool does **not** provide a
cross-resource atomic commit or a network/global replay guarantee.

A person who can tamper with both the DB and the external checkpoint can
construct a consistent replacement state. Stage 246 has no independent
cryptographic signer, hardware counter, monotonic trusted timestamp, secure
enclave or original-PlayStation attestation.

Only synthetic records run in GitHub Actions. No original game contents
or private runtime logs are checked into the project. Static `2708`,
the historical `364` hypothesis, and the independent `88`-byte
initializer remain separate observations; the game's actual record size
and a native Nintendo Switch build remain unverified.
