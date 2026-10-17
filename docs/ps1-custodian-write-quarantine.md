# Stage 263B — durable quarantine of integrated custody writers

This stage extends [Stage 263A](ps1-witness-fence-quiescence-preflight.md).
It adds a one-way **write quarantine** inside the custody SQLite database.
This is a *reference-code fence*, not proof of an independently stopped
service or permission to retire the witness fence.

## Installation

The new `tools.audit_record_custodian_write_quarantine` installer accepts
an exact canonical stage-251 original request, its independently signed
supervisor stop claim, a pinned supervisor Ed25519 public PEM and the
privately held custody/witness databases.

1. Verify the domain-separated Ed25519 supervisor claim, its pinned key,
   the original request commitment, fence owner and all four explicit
   stop/restart/network/writer-access assertions.
2. Open a custody SQLite `BEGIN IMMEDIATE` transaction. Reject an existing
   quarantine, and verify the full custody history, recovery journal,
   reservation state and **negative snapshot** for that exact request.
3. While holding the custody writer lock, check the independent witness
   history, reconciliation audit and **exact** active witness fence in a
   second SQLite `BEGIN IMMEDIATE` transaction.
4. Still holding the custody writer lock, insert a single SHA-256-checked
   `custodian_writer_quarantine` record referencing the request digest,
   fence owner, supervisor proof digest, snapshot classification and
   witness head. Commit custody state atomically.

The witness transaction is rolled back **without changes**. The
quarantine is not a new custody checkpoint, never consumes a reservation,
and does not release the independent witness fence.

```sh
python3 -m tools.audit_record_custodian_write_quarantine \
  /custodian-private/anchors.sqlite \
  /witness-private/recovery-witness.sqlite \
  /custodian-private/original-request.json \
  /witness-private/supervisor-signed-stop.json \
  /witness-private/pinned-supervisor-public.pem \
  PINNED_SUPERVISOR_PUBLIC_PEM_SHA256 \
  --supervisor-tag independent-supervisor
```

Exit 0 means **the instrumented write gate was installed**, not that
every possible writer was disabled. Exit 1 means conflict with the
custody/witness state or existing quarantine; exit 2 means invalid
evidence. The CLI reports no reservation secrets or signing keys.

## Writer enforcement

The following local Python write operations call
`require_unquarantined(con)` from **inside their own custody
`BEGIN IMMEDIATE` transaction, before changing custody state**:

| Mutation entrypoint | Guard coverage |
|---|---|
| `audit_record_custodian_reservation.reserve` | All reservations, including idempotent retries |
| `audit_record_anchor_handoff.deposit` | Legacy, conditional and reserved checkpoint deposits |
| `audit_record_custodian_recovery.recover` | Two-admin reservation retirement, including witness-guarded wrapper |

The mTLS server's `reserve`, `deposit`, and `deposit-reserved`
actions use the same guarded functions. Read-only `latest`, history
inspection and the preparatory administrative proposal remain available.

The lock on custody SQLite serializes quarantine installation against
these patched writers. If a writer commits first, the installer checks
the new state and rejects an incorrectly negative outcome; if quarantine
commits first, subsequent patched writers reject before mutation.

This is a **non-expiring** guard. There is intentionally no automatic
expiry, rollback, administrative unlock or negative-outcome witness
release API. A damaged quarantine row blocks guarded writers.

## Important security limitations

- A signed **claim** about process death, restart blocking and network
  revocation does not verify any operating-system state. Its signatures
  do not establish actual process termination, process identity or
  independent execution.
- A stale executable without these new guards, direct SQLite writes,
  modified binaries, alternate custody files, and other independently
  deployed services are **not** disabled by this table.
- The quarantine row and its hash are inside the same writable SQLite
  database. A malicious administrator who can delete/replace the database
  or table can bypass the guard; SHA-256 checks are not immutable audit
  transparency or hardware-enforced antirollback.
- The supervisor signing key, witness and custody state require separate
  provisioning and access controls. The cross-database transaction is
  not a distributed atomic commit.
- The witness fence remains retained; no negative/uncertain custody
  operation is authorized for witness reconciliation. Later development
  needs externally enforced revocation of all code paths, independent
  verifiable quiescence evidence and separate authorization/audit of
  the negative outcome.

The tests are synthetic: no production custody or witness server has
been deployed, and no Wild Arms PS1/Switch execution is established.
