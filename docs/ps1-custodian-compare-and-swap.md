# Stage 253 — atomic custodian compare-and-swap (CAS)

Stage 252 linked a signed, mutually authenticated TLS custodian to a local
receipt-gated verifier. The custodian previously accepted any checkpoint
with monotonically preserved history. Two different verifiers could fetch
the same receipt and each submit an incompatible but locally consistent
next state, risking a misleading interpretation of their acknowledgments.

Stage 253 adds an **opt-in atomic compare-and-swap** check to custody
deposits. The *network deposit endpoint now requires CAS*; the legacy
stage-248 local `deposit` remains available for compatibility and
must be restricted in any deployment relying on this guarantee.

## Protocol

The verifier must retain the last **independently authenticated**
custodian `sequence` and `receipt_sha256` (the stage-248
domain-separated receipt-chain digest). The stage-252 pending gate stores
both values in its SQLite `receipt_gate` row, in the same transaction
as each locally issued challenge or accepted capture.

A network `deposit` request now includes:

- `expected_sequence`: the prior committed custodian round (positive int).
- `expected_receipt_sha256`: the exact previous receipt-chain SHA-256.
- `checkpoint_b64`: canonical, bounded stage-246 checkpoint bytes.
- The existing random request ID, strict schema and mutual TLS 1.3 identity.

Within the custodian's **single SQLite `BEGIN IMMEDIATE` transaction**:

1. Validate every retained prior receipt and checkpoint.
2. Require both the expected sequence and the expected receipt digest to
   match the **current** custodian head.
3. Accept the new monotonic checkpoint as exactly the next custody round,
   or reject without modifying the custodian ledger.
4. Permit one narrow exception for a network retry after a lost response:
   if the custodian is now exactly `expected_sequence + 1`, its
   **previous receipt digest** equals the caller's expected digest and
   its committed checkpoint bytes have the exact same SHA-256, report
   idempotent success. A different offer or a later round is rejected.

This prevents two concurrent, conflicting proposals based on the same
previous head from both committing. It does not decide which writer
should win; the loser stays in the verifier's pending state and must be
reconciled by an operator.

The TLS client additionally checks that a successful, Ed25519-signed reply
has **exactly** the expected next sequence, links to the expected previous
receipt and contains the **exact checkpoint bytes offered**. Accepting a
later head that merely contains the offered commitments is no longer
treated as proof that this CAS attempt succeeded.

## Commands

For an initial single-shot remote deposit through stage 251, provide the
explicit expected head from a previously trusted custody receipt:

```sh
python3 -m tools.audit_record_custodian_tls deposit \
  127.0.0.1 38481 localhost \
  /verifier-private/tls-client.pem \
  /verifier-private/tls-client-key.pem \
  /verifier-private/trusted-custodian-ca.pem \
  PINNED_SERVER_LEAF_DER_SHA256 \
  /verifier-private/custodian-ed25519-public.pem \
  PINNED_CUSTODIAN_ED25519_PEM_SHA256 \
  /verifier-private/signed-return.json \
  /verifier-private/checkpoint-return.json \
  /verifier-private/checkpoint-offer.json \
  --expected-sequence PREVIOUS_COMMITTED_SEQUENCE \
  --expected-receipt-sha256 TRUSTED_PREVIOUS_RECEIPT_CHAIN_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

For normal operations, use stage-252 `audit_record_remote_admission.py
ack`. It retrieves the expected prior head and the exact pending
checkpoint from **one consistent verifier SQLite snapshot**, submits
CAS over TLS, validates the signed result, and commits the receipt
acknowledgment under a second verifier transaction. If the reply is
lost after custody committed, another `ack` resends **the same
previous head and the same pending bytes**; the custodian reports the
same next round without duplicating it.

The `latest` API and non-network stage-248 legacy methods remain
unchanged. To rely on CAS, restrict alternative write interfaces at
the operating-system and service layer. No production server or
independent credentials are provisioned by this repository.

## Limits and future steps

A race between reading the custodian head and **issuing a local nonce**
is still possible when more than one verifier writes globally: a second
verifier may issue a competing pending operation but it cannot get a
successful CAS deposit after the first wins. An exclusive-writer lease
or an authenticated remote reservation transaction would be required
to prevent even such temporarily stranded local operations.

The custodian is a test-reference SQLite service. Coordinated rollback
of its database and signed-receipt history, malicious key custodians,
bypassing legacy APIs, and untrusted clock/state changes remain outside
the guarantees. This implementation does **not** provide globally
monotonic hardware-backed counters, an independent transparency log,
distributed atomicity, or an authenticated production deployment.

Synthetic tests fork verifier histories and race two conditional
deposits, verify an exactly idempotent retry, reject different/future
offers, and exercise TLS loopback with generated CA/Ed25519 keys.
No original Wild Arms assets, PlayStation hardware execution or
native playable Nintendo Switch build is verified or included.
