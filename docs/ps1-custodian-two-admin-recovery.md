# Stage 256 — two-administrator recovery of an orphaned custodian reservation

Stage 254 deliberately made reservations non-expiring. Losing the verifier's
private 128-bit reservation token therefore permanently blocks that custody
head under the normal protocol. Stage 256 adds an **opt-in, offline,
two-administrator signed reconciliation** for this precise exception.

Implementation: `tools/audit_record_custodian_recovery.py`. The custodian
operator must have direct privileged access to its **private SQLite DB**;
this is not an unauthenticated network or TLS endpoint. The existing
one-shot custodian TLS server does **not** expose recovery.

## Four strict phases

1. The operator confirms, by independent operational investigation,
   that the verifier has **irrecoverably lost its reservation token**.
   This fact cannot be proven cryptographically by the code.
2. `prepare` verifies the entire custody checkpoint history, every previous
   recovery event and the current `reserved` row. It creates an
   **exclusive, mode-0600 private request** with the exact current
   custody sequence, receipt hash, hashed former reservation token,
   a random 128-bit recovery nonce and the single accepted reason
   `irrecoverable-reservation-token`.
3. Two separate administrators independently review **the same private
   request**. Each signs its domain-separated SHA-256 request digest
   using their own Ed25519 private key. Signing does not modify the
   custodian DB. Neither key is committed to GitHub.
4. `recover` verifies both signatures against **two distinct,
   out-of-band-pinned public PEM SHA-256 values and administrator IDs**.
   Under one SQLite `BEGIN IMMEDIATE` transaction it rechecks the entire
   custody and recovery histories, confirms the current reservation
   still matches the exact approved request, appends an SHA-256-linked
   audit event, and **only then retires that one reservation**.

If the custodian head changes, the reservation is already committed,
another operator recovered it, a signature is missing/wrong, or the
recovery journal is corrupted, the action fails without retiring anything.
Two concurrent recovery attempts cannot both win. An old request cannot
retire a replacement reservation because the old token hash no longer
matches the DB.

## Administrator enrollment

Create Ed25519 signing keys independently under two administrator accounts,
as protected private files (mode 0600; parent directory mode 0700):

```sh
openssl genpkey -algorithm ed25519 \
  -out /admin-alice/private-ed25519.pem
openssl pkey -in /admin-alice/private-ed25519.pem -pubout \
  -out /admin-alice/public-ed25519.pem
```

Provision each administrator's **public PEM and exact full-file SHA-256**
to the custodian through separately trusted channels, and protect the
trusted hashes from the party delivering the approvals. Repeat with an
independent key owned by the second administrator.

Two distinct key files/signatures are a cryptographic requirement;
the code cannot prove that they are owned by different humans,
organizations or independent hardware. Separately enforce access-control
separation and a documented administrative approval policy.

## Offline commands

On the custodian, create a private exact-state recovery proposal:

```sh
python3 -m tools.audit_record_custodian_recovery prepare \
  /custodian-private/anchors.sqlite \
  /custodian-private/recovery-request-001.json
```

Each independent administrator approves the **same immutable request** on
their protected signing system:

```sh
python3 -m tools.audit_record_custodian_recovery approve \
  /admin-alice/recovery-request-001.json alice \
  /admin-alice/private-ed25519.pem \
  /admin-alice/approval-001.json

python3 -m tools.audit_record_custodian_recovery approve \
  /admin-bob/recovery-request-001.json bob \
  /admin-bob/private-ed25519.pem \
  /admin-bob/approval-001.json
```

After checking trusted fingerprints, the custodian executes:

```sh
python3 -m tools.audit_record_custodian_recovery recover \
  /custodian-private/anchors.sqlite \
  /custodian-private/recovery-request-001.json \
  /custodian-private/alice-approval-001.json \
  /custodian-private/bob-approval-001.json \
  alice /custodian-private/alice-public-ed25519.pem ALICE_PINNED_PUBLIC_PEM_SHA256 \
  bob /custodian-private/bob-public-ed25519.pem BOB_PINNED_PUBLIC_PEM_SHA256
```

The return code is **0** for committed authorized retirement, **1** if
the previously approved reservation/head changed, or **2** for malformed
or untrusted credentials, an unsafe file, journal corruption or SQLite
error. Public CLI reports contain only redacted booleans and audit
sequence numbers. They never print original tokens, hashes or keys.

## Durable audit and permanent fail-closed behavior

A recovery is recorded in `custodian_recovery_history`, a bounded
SHA-256-linked SQL audit table. Each row commits the recovery-request
digest, head sequence/receipt hash, retired *token hash*, predecessor
event digest and its own event digest. The journal is checked before
subsequent reserved deposits, reservations and further recovery.

**This is a local consistency audit, not an immutable third-party
transparency service**. Anyone who can rewrite the entire custodian DB
or holds the administrator private keys may still falsify history.
For independent rollback resistance, the operator should export and
externally attest the recovery journal hash using a protected custodian
or witness service; this stage does not build that external anchor.

Once any recovery journal exists, **legacy/unreserved deposits remain
prohibited**, even while there is no current reservation row. This is
essential: the approved recovery must allow a **new reserved verifier**
to take over the same custody head, not reopen older unchecked writes.

Recovery does not automatically grant the former verifier access or
preserve an old pending local capture. A former owner might remain
online and try to submit its original pending checkpoint; its token is
now rejected. Administrators must reconcile the old verifier separately.

## Explicit limitations

- The decision that a token was truly lost is **an operational assertion**,
  not something that Ed25519 or a local database can prove.
- No automatic expiry, one-admin override, arbitrary cancellation, or
  forced deletion of an already committed reservation is allowed.
- No independent production custodian, signed external recovery ledger,
  key-rotation/revocation mechanism, TPM-backed counter or remote
  administrative API is deployed.
- Original Wild Arms PS1 execution, real debugger evidence, proprietary
  asset authenticity and a playable Nintendo Switch game are not proven.

Synthetic CI uses temporary independent Ed25519 keys and SQLite files only.
