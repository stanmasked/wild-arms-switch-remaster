# Stage 257 — independently retained recovery witness

Stage 256 stores a hash-linked administrative recovery journal in the same
SQLite database as the custodian checkpoint ledger. A sufficiently privileged
actor could roll **both** back and present a locally self-consistent but
incomplete history.

Stage 257 introduces an **opt-in independent recovery witness**:
`tools/audit_record_recovery_witness.py`. The witness maintains its **own**
private SQLite database with an immutable-prefix append-only sequence of
the exact recovered administrative audit events and signs its current
high-water state using a separately owned Ed25519 key.

This is a reference offline custody workflow; the project does not deploy
or independently operate a production witness.

## Protocol

1. The custodian executes a fully authorized stage-256 recovery, where
   two administrators have already approved the retirement. That recovery
   and its hash-linked audit event commit atomically to the custodian DB.
2. `capture` reads the complete custody checkpoint and recovery histories
   in **one SQLite read transaction**, validates their chains and creates
   a bounded, mode-0600 exclusive private recovery snapshot.
3. Deliver the snapshot to a **separately administered** witness with
   independent control over its own database and signing key.
4. `record` checks all events, including the original stage-256 event
   SHA-256 links. Under **one witness SQLite BEGIN IMMEDIATE transaction**,
   it verifies that every previously witnessed event matches the candidate
   byte-for-byte. Only a monotonic extension is accepted; an exact retry
   after a lost response is idempotent. A shorter or rewritten prefix is
   rejected.
5. `sign` reads the latest **committed** witness head and signs its
   event count, final recovery event SHA-256 and independent witness-chain
   hash using Ed25519 with a domain-separated canonical message. A failure
   after `record` does not require recording the same events again; the
   operator can repeat `sign` using a fresh exclusive output filename.
6. `verify` authenticates that receipt against an **out-of-band-pinned
   public PEM SHA-256**, compares the signed receipt against the actual
   high-water record retained in the independent witness DB, then checks
   the custodian's *current* full recovery journal against every retained
   witness event.

A custodian rollback with fewer than the witnessed events, or a
self-consistent rewritten history with different recovery events, fails.
A genuinely signed but outdated witness receipt also fails if the
independent witness has accepted a newer event.

The verifier may use `--require-exact` to reject newly committed local
recovery events that have **not yet been independently witnessed**.
Without that flag, it reports the number of newer unwitnessed events
instead of inventing a rollback.

## Example offline commands

Capture locally at the custodian:

```sh
python3 -m tools.audit_record_recovery_witness capture \
  /custodian-private/anchors.sqlite \
  /custodian-private/recovery-snapshot-001.json
```

After authenticated transfer of that private file to a distinct witness
account/machine, append the event sequence there:

```sh
python3 -m tools.audit_record_recovery_witness record \
  /witness-private/recovery-witness.sqlite \
  /witness-private/recovery-snapshot-001.json
```

The witness alone uses its private Ed25519 key to sign the now-committed
head and privately deliver the receipt:

```sh
python3 -m tools.audit_record_recovery_witness sign \
  /witness-private/recovery-witness.sqlite \
  /witness-private/witness-private-ed25519.pem \
  /witness-private/signed-witness-001.json \
  --witness-tag wild_arms_external_recovery_witness
```

Verify on a trusted auditor host, with independent access to the witness
DB or a separately authenticated equivalent:

```sh
python3 -m tools.audit_record_recovery_witness verify \
  /custodian-private/anchors.sqlite \
  /witness-private/recovery-witness.sqlite \
  /audit-private/signed-witness-001.json \
  /audit-private/witness-public-ed25519.pem \
  TRUSTED_WITNESS_PUBLIC_PEM_SHA256 \
  --witness-tag wild_arms_external_recovery_witness --require-exact
```

All private inputs, key files and databases require protected filesystem
permissions (mode-0600 files in mode-0700 directories). Never place
private original game data, recovery credentials or signing keys in
GitHub. The public success output includes only high-water counts and
redacted status fields.

## Crash and adversarial cases

| Event | Response |
|---|---|
| Custodian recovery committed; capture not yet delivered | Newest recovery is not yet witnessed, detectable with strict verification |
| Witness record committed; reply lost | Re-submit exact snapshot, returns idempotent result |
| Witness record committed; signing response lost | Sign latest committed head again to a fresh private path |
| Custodian history rolled back to before a witnessed recovery | Verification fails |
| Custodian recovery journal rewritten with locally recomputed hashes | Event-by-event comparison fails |
| Older genuine signed receipt replayed after a new witnessed recovery | Verification refuses stale head |
| Wrong witness signing key / substituted public PEM | Verification refuses signature or trusted-key pin |
| Damaged witness SQLite event content or chain | Recording and verification fail closed |
| Two concurrent identical witness submissions | A single append occurs under SQLite writer lock |

## Trust boundaries and unresolved risks

**An external witness is useful only if its database, private signing key
and independently provisioned public-key pin are outside the custodian's
control.** Merely creating two SQLite files under one administrator does
not establish independent protection. The repository provides no
production deployment, authenticated transport between operators, key
revocation/rotation or an immutable transparency service.

This version does **not** automatically run `verify` before every
custodian reservation, deposit or administrative recovery; existing
interfaces continue to work even if the operator omits witnessing.
An uncompromised independent witness can expose a rollback **when
consulted**, but cannot prevent recovery-history gaps committed after its
latest signed high-water. The witness DB and signed receipt are both
required here for freshness; the signature alone does not prove that
the presented receipt is the globally latest one.

This does not provide distributed atomicity between custodian and
witness databases, hardware rollback-proof counters or independent
confirmation of original PlayStation execution. Tests use only synthetic
SQLite data and temporary Ed25519 keys; no real Wild Arms assets or
playable Nintendo Switch game build are verified.
