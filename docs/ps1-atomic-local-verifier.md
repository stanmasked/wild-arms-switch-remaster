# Stage 245 — verifier-owned, atomic local PS1 capture acceptance

Stage 244 checked capture reuse **relative to a provided ledger and provided
challenge**. Both could be replaced by the submitter. Stage 245 introduces a
separate verifier-operated tool, `tools/audit_record_atomic_verifier.py`,
which **issues** its own random challenge and **atomically** commits
single-use acceptance into a private local SQLite database.

The existing stage-242, stage-243 and stage-244 evidence formats and
read-only analyzers remain unchanged. Stage 245 reruns the entire stage-243
EXE/temporal/JSONL/provenance chain, so acceptance cannot skip it.

## Prerequisites and trust boundary

The verifier operator must control a **private directory and database** on a
trusted local filesystem, kept separate from the capture producer. File owner
must match the verifier process, and both directory and DB must not grant
any permissions to group/other users. DB is created with mode `0600`; use
a verifier-owned directory with mode `0700` (for example,
`/private/verifier`). Do not commit this DB, its SQLite journal, its
one-time challenges, original game files, or capture outputs to GitHub.

This is designed for a **single machine with SQLite-compatible local file
locking**. Do not use an NFS or untrusted shared filesystem. File permissions
do not protect against a malicious process under the *same* OS account,
compromise of the verifier, privileged access, rollback/restoration of DB
backups, deletion of the database, physical tampering, clock manipulation,
or another verifier using a different database. Those threats require
additional trusted infrastructure.

## Operation

**1. Create a one-time verifier-issued challenge before capture.**

```sh
mkdir -m 700 -p /private/verifier
python3 -m tools.audit_record_atomic_verifier issue \
  /private/verifier/captures.sqlite --ttl-seconds 300
```

The issuer uses `secrets.token_hex(16)` (128 unpredictable bits) for
a nonce and records its issuance and expiry in SQLite. The issuance command
prints this nonce **so the operator can deliver it to the recorder via a
private channel**. Do not publish or check in the issuance response.

Supported TTL range: **30–3600 seconds**, default 300. Expiry uses the local
verifier's wall clock; that clock is not attested. The recorder must put the
issued nonce into the *stage-243 provenance JSON* and the two stage-243
collector receipts. The recorder must **not** choose a different nonce.

**2. Collect the normal stage-243 evidence, privately.**

Keep the user-owned disc, inventory, temporal claim, raw JSONL streams,
SHA-256 binding manifest, provenance and receipts **outside CI**.

**3. Verify and consume the challenge atomically.**

```sh
python3 -m tools.audit_record_atomic_verifier accept \
  /private/verifier/captures.sqlite \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl \
  /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json \
  /private/after-receipt.json
```

The local acceptance gate first runs all stage-243 checks. If they are
consistent, it starts a SQLite `BEGIN IMMEDIATE` transaction, then:

- confirms that the exact claimed nonce was previously **issued by this
  verifier**, has not been consumed, and has not expired;
- inserts the SHA-256 of the exact provenance bytes as a unique accepted
  digest, together with the nonce and local acceptance time;
- inserts **both** raw JSONL stream hashes into one unique digest table
  to prevent cross-role reuse under another nonce;
- marks the issued challenge consumed in the **same transaction**;
- commits the acceptance together with those uniqueness constraints.

Any collision or failure rolls the transaction back, leaving no partial
acceptance. A second concurrent acceptance of the same capture cannot win:
only one writer can hold the transaction, and later submissions see the
consumed challenge or duplicate digest.

No part of this tool updates or exports the previous stage-244 JSON ledger.
The SQLite acceptance history is intentionally independent and not
limited to 512 rows.

## Report and exit status

The **issue** command reports the freshly minted nonce and TTL *only* for
private delivery. The **accept** command reports a redacted JSON object:
whether one-time acceptance succeeded, with explicit false flags for
independent hardware/debugger/database attestation.

- **0**: acceptance completed atomically.
- **1**: valid inputs but evidence inconsistent, nonce absent/expired/spent,
  or digest already accepted.
- **2**: corrupted, unreadable, malformed or oversized evidence, or invalid
  verifier DB. Public error is only `invalid_private_input`.

There are no reported source addresses, memory values, EXE/debugger hashes,
journal paths, session nonces or raw records in the acceptance result.
The tests run on synthetic EXEs and invented memory values only; no game data
is committed or uploaded.

## What this does *not* establish

An operator can create a self-consistent simulated capture using a real
verifier-issued nonce: the database does **not** authenticate the debugger,
the collector, emulator timing, or PS1 hardware execution. It cannot
distinguish truthful or fabricated stage-243 logs that agree internally.

SQLite commit durability depends on the local OS, filesystem and storage
honouring SQLite's sync/locking guarantees, and not on a cryptographic
ledger attestation. Even a consumed nonce can be replayed after a malicious
database rollback or by a second verifier using different state. Reaching a
stronger cross-machine trust boundary would require externally anchored
append-only history, strict verifier identities, protected keys, and hardware
or runtime provenance.

The static `2708` multiplier in checked-in machine code remains distinct
from any independently established Wild Arms structure size, and **no native
Nintendo Switch game build** is certified by this work.
