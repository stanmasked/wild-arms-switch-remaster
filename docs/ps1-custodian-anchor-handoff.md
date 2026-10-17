# Stage 248 — custodian checkpoint handoff and recoverable receipts

Stage 247 provides an **opt-in** SQLite admission gate against a private
checkpoint that a verifier supplies. It cannot atomically commit a local
SQLite update *and* a checkpoint in an independent custodian's database.
Stage 248 introduces an **explicit handoff and crash-recovery reference
protocol** for an operator-controlled custodian:

- `tools/audit_record_anchor_handoff.py prepare` creates the stage-246
  exact-state checkpoint in a private file.
- `deposit` durably commits that exact byte sequence to a **separate
  private SQLite database** under the custodian's control, with a monotonic
  integer sequence and a SHA-256 hash-linked receipt chain.
- `receipt` creates an immutable private confirmation from the committed
  custodian history. **It can be rerun after a crash** following the deposit
  commit without needing to repeat or roll back the deposit.
- `verify` compares a supplied private receipt to the *latest* committed
  custodian entry; stale or modified receipts cannot pass this check.
- `export` writes the latest committed checkpoint as a new private file
  for use as the input to the stage-247 guarded admission interface.

All inputs and artifacts are private: only counts, commit sequence numbers
and boolean results appear in CLI stdout. The actual checkpoint hashes,
recorder nonces and receipt digests are restricted to private files and the
custodian database.

## Reference workflow

Use separate private directories (mode 0700). In a real deployment the
**custodian must operate under a separate trusted identity or boundary**:
running all commands as the same verifier account protects against
accidental state divergence, not a compromised verifier. This repository
does not deploy a remote custodian or configure independent OS identities.

```sh
python3 -m tools.audit_record_anchor_handoff prepare \
  /private/verifier/sessions.sqlite \
  /private/verifier/outgoing/checkpoint-001.json
```

Transfer the checkpoint to the custodian via a private authenticated channel
(outside the scope of this reference tool). Then, under the custodian account:

```sh
python3 -m tools.audit_record_anchor_handoff deposit \
  /custodian-private/anchors.sqlite \
  /custodian-private/inbox/checkpoint-001.json

python3 -m tools.audit_record_anchor_handoff receipt \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/receipt-001.json

python3 -m tools.audit_record_anchor_handoff verify \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/receipt-001.json

python3 -m tools.audit_record_anchor_handoff export \
  /custodian-private/anchors.sqlite \
  /custodian-private/outbox/anchored-checkpoint-001.json
```

The exported checkpoint can be transferred back to the verifier via a
separately authenticated channel and passed to
`audit_record_guarded_admission.py issue` or `accept`.

The deposit refuses a checkpoint that omits any commitment in the previously
accepted custodian state. It permits later issued or accepted sessions,
enforces a strict sequence and validates every previously retained
checkpoint and receipt-chain link. An identical repeat of the **latest**
deposit is idempotent; replay of an earlier state after a newer deposit is
rejected. Exports use the exact persisted byte sequence, not a recreated
version.

## Failure and recovery matrix

| Failure point | Persisted state | Recovery |
|---|---|---|
| Before `deposit` commit | No new custodian round | Retry `deposit` |
| After `deposit` commit, before receipt file | New committed round exists | Retry `receipt` (no new round) |
| Receipt file created but delivery fails | Committed round and private receipt | Produce another receipt at a **new** file path |
| Same checkpoint submitted twice | One round only | Second `deposit` reports idempotence |
| Older checkpoint submitted after newer state | Newer state retained | Reject stale offer |
| Receipt for an earlier round presented as latest | Newer round retained | `verify` rejects old receipt |

Receipt output uses exclusive file creation and cannot silently overwrite an
existing private file. Database writes use SQLite `BEGIN IMMEDIATE`,
`synchronous=FULL`, unique checkpoint and receipt digests, and rollback on
failure. This is local SQLite durability, **not** atomicity across the
verifier and custodian databases. Up to 256 custody rounds and stage-246's
640 KiB checkpoint limit are supported, with fail-closed bounded reads.

## Claims we explicitly do not make

**No independent trust anchor is provided by this code alone.** If the same
person/process can roll back both SQLite files or forge the channel's
custodian response, the hash chain can be rewritten and replay prevention is
not guaranteed. No signatures, hardware roots of trust or network quorum
have been implemented. Receipt matching alone is not proof of independent
custodian acknowledgment.

Between the verifier's local acceptance and the custodian's subsequent
acknowledgment, a crash can still lose unanchored local operations. The
stage-247 opt-in interface does not automatically require a fresh receipt
before its next operation, and the legacy stage-245 interface remains
unguarded. A true cross-system high-water admission policy and authenticated
handoff channel are **future integration work**.

Synthetic tests simulate two logically separated private directories and
crashes, not two mutually isolated computers or accounts. Original Wild
Arms PS1 execution, actual record size and a native Nintendo Switch
game build remain unverified.
