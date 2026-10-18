# Stage 263Q — locally recorded independent escrow publications

Stages 263O–P verify complete signed archives **provided by the operator**.
They cannot tell whether another operator previously published a
different, validly signed receipt and later withdrew it.

Stage 263Q adds `tools.audit_record_witness_publication_intake`, a
**separate, explicitly initialized private SQLite intake journal**.
It accepts *individual* Stage 263O three-operator receipt envelopes in
their signed roles, checks the accepted Stage 263N registry and logs
first-seen receipts in an SHA-256-linked sequence. When a signer
presents a valid but inconsistent receipt, the intake records the
contradiction as a separate **conflict event** without overwriting the
first receipt. It then refuses every later submission until independent
investigation.

**This is a local research prototype, not a deployed remote
independent publication or transparency service.**

## External pins and initialization

Run `init` once in a private directory on an independently operated
host, distinct from custody and the accepted registry:

```sh
python3 -m tools.audit_record_witness_publication_intake init \
  /independent-private/escrow-publications.sqlite
```

Creation uses exclusive file creation; `inspect` and `submit` never
implicitly reset or create a missing journal. Keep the journal 0600
in a private directory.

Maintain the latest **intake event count** and **intake head SHA-256**
independently. For each submission, also provide the separately
retained Stage 263N accepted registry count, head SHA-256 and latest
accepted checkpoint SHA-256. Values learned only from an untrusted
host are not independent pins.

## Submit each operator's signed receipt

One command publishes one exact Ed25519 signed envelope (not the
reduced JSON body):

```sh
python3 -m tools.audit_record_witness_publication_intake submit \
  /independent-private/escrow-publications.sqlite \
  /independent-private/accepted-checkpoints.sqlite \
  /private/escrow-a-genesis-signed.json \
  escrow-a \
  /operator-a/public.pem INDEPENDENTLY_PINNED_A_PEM_SHA256 \
  --checkpoint-tag private-wild-arms-ledger \
  --expected-count INDEPENDENT_INTAKE_EVENT_COUNT \
  --expected-head INDEPENDENT_INTAKE_HEAD_SHA256 \
  --expected-registry-count INDEPENDENT_REGISTRY_EVENT_COUNT \
  --expected-registry-head INDEPENDENT_REGISTRY_HEAD_SHA256 \
  --expected-checkpoint INDEPENDENT_LATEST_ACCEPTED_CHECKPOINT_SHA256
```

Use `escrow-b` and `escrow-c` with their respective enrolled
public keys for the other receipts. Only individually valid signed
claims can enter the journal.

For every round, publish all three operator receipts before moving
to the next accepted registry checkpoint; begin with round 0
(genesis). Every accepted receipt must match the exact enrolled
registry event SHA-256 and checkpoint SHA-256, the three operators
must agree on the same round nonce and prior escrow digest, and the
signed predecessor escrow SHA-256 must equal the domain-separated
hash of the three signed envelopes in the preceding round.

An exact replay of the same receipt is rejected without creating
another event. A different valid signed receipt for the same
`(round, role)`, a conflicting peer nonce, a claimed registry hash
not matching that round, a missing previous round, or an incorrect
signed predecessor leads to an appended conflict event and a
permanently **conflict-frozen local intake**. The only safe resolution
is external human-led investigation and a separately reviewed
recovery procedure; no reset or automatic reconciliation exists.

A conflict submission returns exit code **1** and JSON
`signed_conflict_recorded=true` with the **updated** event count/head.
The operator must independently preserve this newly committed head
even though the command failed. Other rejected submissions do not
advance the journal. Exit code **0** means one valid first-seen
receipt was appended. Exit code **2** means invalid input or an OS
failure.

## Read-only audit

```sh
python3 -m tools.audit_record_witness_publication_intake inspect \
  /independent-private/escrow-publications.sqlite \
  --expected-count INDEPENDENT_INTAKE_EVENT_COUNT \
  --expected-head INDEPENDENT_INTAKE_HEAD_SHA256
```

Inspection verifies the SQLite schema and header, denies added
triggers/views/indexes, walks each prior event SHA-256, checks
sequence numbers, unique accepted slots and original receipt
commitments in any conflict event. It checks the current event
count/head against independently supplied values. It does not
retrieve historical signed envelope bytes from private archives or
reverify old signatures during inspection: only their exact SHA-256
hashes are committed. Retain every original signed envelope
independently to reproduce signature verification.

## Security boundary

The local SQL journal is NOT physically immutable. A privileged actor
who restores both an older database and matching older externally
retained pins can still hide later publications or conflicts.
Checks of the accepted registry and intake are not one cross-database
atomic transaction. The verifier cannot discover other operator
machines, hidden equivocation or true global freshness. Public key
pins are externally enrolled by the operator: this tool does not
establish independent identities for those machines.

`complete_remote_publication_proved=false`,
`all_equivocations_discovered=false`,
`independent_latest_head_storage_proved=false`,
`rollback_prevention_proved=false`,
`witness_fence_retirement_authorized=false` and
`witness_fence_retired=false` remain in the report, even on success.

No original PlayStation code was re-executed or Nintendo Switch
gameplay verified as part of these synthetic tests. There is no
witness-fence release in this tool.
