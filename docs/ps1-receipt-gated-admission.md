# Stage 249 — receipt-gated, one-operation-at-a-time PS1 verifier admission

The stage-247 verifier can commit multiple SQLite changes after its most
recent external checkpoint. Stage 248 can durably deposit checkpoints in a
separate custodian database and recover receipts after a crash, but does not
tie each issue/accept transaction to a required custodian confirmation.

Stage 249 adds an **opt-in admission interface**:
`tools/audit_record_receipt_gated_admission.py`. It is strict:
**one new issue or acceptance at a time**, then no further admission until
the resulting checkpoint has been deposited and acknowledged by the
custodian. It does not silently fall back to an older checkpoint.

## Durable state transitions

The verifier's private SQLite database gains a one-row
`receipt_gate` table with:

- Last acknowledged custodian sequence and receipt-chain digest.
- Optional pending custodian sequence and exact checkpoint-byte SHA-256.

The table is created only by explicit **bootstrap**. The verifier
must already have a stage-245 database, and the custodian must already
have a stage-248 **committed checkpoint of that exact logical state**.
Bootstrap verifies a private latest custodian receipt and exact state
equality before it creates the row. Re-bootstrap is deliberately refused.

For every `issue` or `accept` call:

1. The caller supplies the latest private custodian receipt and the
   custodian's private SQLite database through a trusted operational boundary.
2. Inside the verifier's `BEGIN IMMEDIATE` transaction, reject any pending
   operation, any changed custodian high-water sequence/receipt, or any
   unanchored local database difference, **even an additional record**.
3. Perform the stage-245 issue or stage-243-validated capture acceptance.
4. Compute the stage-246 logical checkpoint commitment of the resulting
   *uncommitted* transaction state.
5. Store the resulting pending checkpoint digest and expected next
   custodian sequence **in that same SQLite transaction**, then commit.

This is the key crash-safety guarantee within **one** SQLite DB: an
accepted/issued record cannot be committed without also recording that
its subsequent custodian acknowledgment is outstanding.

To acknowledge, a custodian deposits the exact resulting checkpoint
using stage 248. Then `ack` checks the latest custody receipt, prior
receipt-chain digest, expected sequence, pending checkpoint digest and
current verifier logical database state. The pending marker is removed
**only after all these match**. A repeated `ack` for the same committed
receipt is safe and idempotent.

## Operator workflow

Every directory must be private (mode 0700) and DB files mode 0600.
The custodian must be independently operated and its checkpoint/receipt
delivery authenticated by the operator; the repository does not deploy
those trust boundaries.

First issue an initial stage-245 challenge, create a stage-246
checkpoint, and deposit it with stage 248 as the **bootstrap anchor**.
This can be a verifier-owned database with no accepted captures or an
already validated older state.

On the verifier (using trusted private copies of the custodian database
and its latest receipt in this reference implementation):

```sh
python3 -m tools.audit_record_receipt_gated_admission bootstrap \
  /private/verifier/sessions.sqlite \
  /custodian-private/anchors.sqlite \
  /custodian-private/receipt-001.json
```

Make exactly one new operation, for example issue:

```sh
python3 -m tools.audit_record_receipt_gated_admission issue \
  /private/verifier/sessions.sqlite \
  /custodian-private/anchors.sqlite \
  /custodian-private/receipt-001.json
```

The issuer returns the newly generated 128-bit nonce **for private delivery
to the collector**. Subsequent issue/accept calls now fail closed.

Prepare the resulting exact-state checkpoint, deposit and retrieve the
custodian's latest private receipt:

```sh
python3 -m tools.audit_record_anchor_handoff prepare \
  /private/verifier/sessions.sqlite \
  /private/verifier/outgoing/offer-002.json

python3 -m tools.audit_record_anchor_handoff deposit \
  /custodian-private/anchors.sqlite \
  /custodian-private/inbox/offer-002.json

python3 -m tools.audit_record_anchor_handoff receipt \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/receipt-002.json
```

Use a **new private file name** for every receipt/offer; stage 248 refuses
overwriting an existing file. After authenticated private delivery:

```sh
python3 -m tools.audit_record_receipt_gated_admission ack \
  /private/verifier/sessions.sqlite \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/receipt-002.json
```

Only now may the verifier issue the next nonce or accept the pending
collector's complete stage-243 capture. Acceptance uses the same arguments
as stage-245, preceded by both the custodian DB and current receipt:

```sh
python3 -m tools.audit_record_receipt_gated_admission accept \
  /private/verifier/sessions.sqlite \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/receipt-002.json \
  /private/WildArms.bin /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json /private/capture-manifest.json \
  /private/before-watch.jsonl /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json /private/after-receipt.json
```

After successful acceptance, the gate again remains pending until the
new post-acceptance checkpoint is deposited and acknowledged.

## Crash recovery

| Failure | Safe state and recovery |
|---|---|
| Before verifier transaction commit | No new challenge/evidence and no pending marker |
| After verifier commit but before deposit | Pending marker survives restart; prepare and deposit the committed checkpoint |
| After custodian deposit, before receipt delivery | Pending remains; reissue stage-248 private receipt without duplicating custodian state |
| After receipt delivery, before verifier `ack` | Pending remains; repeat `ack` using the same latest receipt |
| After verifier `ack` commits but acknowledgment reply is lost | Repeat `ack` idempotently |
| Local DB changed through a legacy API | Expected exact checkpoint no longer matches; subsequent admission or `ack` fails closed |
| Custodian rolled back to older state | Local high-water differs; normal admission is denied |

Exit code **0**: issue/accept/bootstrap/ack committed (or idempotent
ack). **1**: blocked on pending handoff, stale/mismatched receipt or
ineligible capture. **2**: malformed/unsafe input, corrupted history,
missing verifier gate or permission error. Acceptance and acknowledgment
reports reveal no private hashes, paths, addresses, game values or
session nonces. Only `issue` exposes its newly minted nonce, intentionally.

## Threat model and explicit limitations

This is a **reference local implementation, not a deployed remote
custodian**. Its supplied custodian DB and receipt are read on the same
machine with the process's local permissions. The code can establish
relative checkpoint agreement but **not independent custodian identity**
or authenticated network response. Two coordinated local database
rollbacks, a compromised verifier/custodian identity, forged private
receipt/channel, or malicious machine clock can still defeat the protection.

There is no atomic transaction spanning the verifier and custodian
databases. Crash recovery works by durable pending state, but a lost
unanchored verifier commit can still occur if its entire local database
is rolled back before an external deposit. Until custody has recorded the
checkpoint, independent rollback prevention is not guaranteed.

The older stage-245 and stage-247 issue/accept interfaces are still
accessible and bypass the stage-249 opt-in gate. Deployments must forbid
use of those commands through permissions, process isolation or an
exclusive service interface. This implementation does **not** claim all
verifier operations are universally gated.

All tests use synthetic assets. Original PlayStation hardware execution,
the actual Wild Arms record structure size and native Nintendo Switch
build remain unverified.
