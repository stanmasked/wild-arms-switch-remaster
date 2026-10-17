# Stage 255 — reserve custody before accepting a PS1 capture

Stage 254 introduced a durable remote custody reservation before **challenge
issuance**. Captured evidence could still be accepted through stage-252's
remote interface without reserving the head, leaving a competing-verifier
window. Stage 255 adds a **separate opt-in reserved acceptance** flow in
`tools/audit_record_remote_reserved_accept.py`.

## Full private acceptance protocol

1. Query the custody head through the existing mutually authenticated
   TLS 1.3 channel and verify its pinned Ed25519 receipt.
2. **Before acquiring any non-expiring reservation**, validate the entire
   stage-243 provenance bundle and check the local SQLite challenge under
   `BEGIN IMMEDIATE`: the nonce must exist, be unconsumed and unexpired;
   both captured stream hashes and provenance hash must be unused.
   Invalid, expired, missing or previously consumed captures never reserve
   the remote custody head.
3. Under the verifier's `BEGIN IMMEDIATE` transaction, persist the same
   stage-254 recovery token and expected custody version. Stage 255 also
   stores the operation **purpose** (`accept` versus `issue`) and a
   domain-separated SHA-256 commitment of the exact length-delimited
   eight input byte streams. A retry must use the **same evidence bundle**.
   Cross-purpose or different-evidence attempts cannot borrow the
   previously retained reservation token.
4. Send stage-254 `reserve` over TLS. The custodian exclusively reserves
   the current history head. A competing verifier is rejected **before**
   any local capture acceptance occurs.
5. Once the signed reservation acknowledgment matches the exact expected
   head, run the full stage-249 capture validation again inside its
   acceptance path; atomically consume the challenge, accept its three
   logical evidence commitments and persist the pending next checkpoint.
6. Run `audit_record_remote_reserved_accept.py ack`, which uses stage-254's
   common `acknowledge_reserved` flow to deliver the exact pending
   checkpoint under the saved token. A lost response is safely retried,
   with the custodian accepting only the exact immediate next state.

A new copy of the custodian's SQLite database is **not** required on the
verifier. All evidence stays private and public CLI reports contain no
previously issued nonce, memory value, stream digest or reservation token.

## Backward compatibility and fail-closed policy

Existing stage-254 databases have a four-column
`remote_issue_reservation` table. The first subsequent new reservation
adds `purpose` (default `issue`) and `evidence_sha256` columns under
the verifier's write lock. Existing issue tokens and pending acknowledgments
remain valid. Read-only inspection/acknowledgment can still read the older
four-column schema; malformed or partial schemas are rejected.

To reduce accidental bypass, the stage-248 local custodian `deposit`
operation now **refuses all unreserved writes once a custodian reservation
row exists**, even after that reservation has been committed.
This makes reservation mode effectively persistent for the given custodian
SQLite database. The existing TLS `deposit` action is likewise refused
by the server because it calls the same custodian commit function.

**This is not universal enforcement.** A privileged actor who can alter
the custodian DB, drop the reservation row or call older verifier commands
can still bypass the new path. Operators must restrict legacy commands and
independently protect ownership of both databases, keys and TLS endpoints.
Stage 254's existing unreserved test bootstrap continues to work before
any reservation has been activated.

## Usage

First use stage 252's signed remote bootstrap to synchronize the verifier
with the custodian, then use stage 254 reserved `issue` and `ack` to
create and anchor a nonce. Captured evidence can then be processed with:

```sh
python3 -m tools.audit_record_remote_reserved_accept accept \
  /verifier-private/sessions.sqlite \
  127.0.0.1 38481 localhost \
  /verifier-private/tls-client.pem \
  /verifier-private/tls-client-key.pem \
  /verifier-private/trusted-custodian-ca.pem \
  PINNED_SERVER_LEAF_DER_SHA256 \
  /verifier-private/custodian-ed25519-public.pem \
  PINNED_CUSTODIAN_ED25519_PUBLIC_PEM_SHA256 \
  /private/WildArms.bin /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json /private/after-receipt.json \
  --custodian-tag wild_arms_custodian_01
```

Start a separate stage-251 `serve-once` server for **each** network
exchange (`latest`, `reserve`, then `deposit-reserved`). After a
successful acceptance the local gate is pending and blocks all new
stage-249-compatible operations. To finalize:

```sh
python3 -m tools.audit_record_remote_reserved_accept ack \
  /verifier-private/sessions.sqlite \
  127.0.0.1 38481 localhost \
  /verifier-private/tls-client.pem \
  /verifier-private/tls-client-key.pem \
  /verifier-private/trusted-custodian-ca.pem \
  PINNED_SERVER_LEAF_DER_SHA256 \
  /verifier-private/custodian-ed25519-public.pem \
  PINNED_CUSTODIAN_ED25519_PUBLIC_PEM_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

A lost reserve response preserves the exact local recovery token, and
retrying acceptance with **identical** evidence is idempotent at the
custodian. If the local acceptance already committed but the CLI reply
was lost, **do not retry acceptance**: the pending marker prevents a
second acceptance. Instead retry `ack`; it deposits the existing
checkpoint without spending a second nonce.

## Remaining deployment limitations

No production remote custodian, independent key enrollment,
administrative revocation/abandonment, trusted hardware counter or
cross-database atomicity has been implemented. Reservations deliberately
have no clock-based expiry: permanent loss of the private recovery token
requires independently authorized administrative reconciliation, which
will be a separate audited feature. Multiple independent processes could
still race between local evidence preflight and remote reservation; the
custodian ensures only one owner and the final SQLite transaction still
rejects consumed challenges.

GitHub Actions runs on synthetic test evidence and temporary local TLS
certificates, not original proprietary PlayStation game assets.
Original Wild Arms PS1 execution, actual record structure size and
a playable Nintendo Switch remaster have not been confirmed.
