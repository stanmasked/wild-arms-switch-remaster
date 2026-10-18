# Stage 263N — accepted checkpoint registry and fork detection

Stage 263L stores signed observer-run claims in a private replay journal.
Stage 263M verifies a replay-journal head endorsed by two independent
Ed25519 administrator keys. Neither stage independently decides which
of two competing, valid signed heads should be accepted.

Stage 263N adds a SECOND SQLite file with an atomic, hash-chained
register of accepted Stage 263M checkpoints. The tool has three
commands: init, accept, inspect. It has no reset or witness-fence
retirement command.

## Trust and operation

First initialize a new file in a private directory:

    python3 -m tools.audit_record_witness_checkpoint_registry init \
      /independent-private/accepted-checkpoints.sqlite

Retain the returned triple — registry event count, registry head
SHA-256, latest accepted checkpoint SHA-256 — INDEPENDENTLY and
outside the host that can write this registry. The genesis values
are event count 0, a domain-separated registry genesis digest and
the Stage 263M ANCHOR_GENESIS prior checkpoint digest.

To accept a new checkpoint, provide:

- Stage 263L replay-journal file;
- Stage 263M admin-a and admin-b signed checkpoint envelopes, exact
  separately pinned public keys, checkpoint scope and predecessor;
- an independently determined candidate checkpoint SHA-256;
- the independently retained CURRENT registry count/head/checkpoint.

Example:

    python3 -m tools.audit_record_witness_checkpoint_registry accept \
      /independent-private/accepted-checkpoints.sqlite \
      /independent-private/observer-replay.sqlite \
      /private/admin-a-signed-head.json \
      /private/admin-a-public.pem ADMIN_A_PUBLIC_SHA256 \
      /private/admin-b-signed-head.json \
      /private/admin-b-public.pem ADMIN_B_PUBLIC_SHA256 \
      --checkpoint-tag private-wild-arms-ledger \
      --prior-checkpoint-sha256 PRIOR_CHECKPOINT_SHA256 \
      --candidate-checkpoint-sha256 CANDIDATE_CHECKPOINT_SHA256 \
      --expected-count RETAINED_REGISTRY_COUNT \
      --expected-head RETAINED_REGISTRY_SHA256 \
      --expected-checkpoint RETAINED_LATEST_CHECKPOINT_SHA256

The verifier first validates both independently pinned Ed25519
signatures, distinct key material, nonce, signed scope and the replay
journal's exact count/head. It then locks the accepted-checkpoint
registry in a single SQLite BEGIN IMMEDIATE transaction and audits
its complete SHA-256-linked history before appending.

The current registry count/head must equal the externally retained
values; the signed predecessor and externally retained latest
checkpoint must both match the current registry tip. The new
checkpoint count must be GREATER than the previously accepted replay
event count. Previously accepted checkpoint nonces, repeated
checkpoint digests and silently changed scope are rejected.

Two concurrent proposals using the SAME previous externally retained
head cannot both commit: only the first atomic append can succeed.
An invalid signature or stale external registry head does not append.

After each successful acceptance, independently retain the NEW triple.
The tool does not independently transmit or durably escrow it.

Read-only checking:

    python3 -m tools.audit_record_witness_checkpoint_registry inspect \
      /independent-private/accepted-checkpoints.sqlite \
      --expected-count RETAINED_REGISTRY_COUNT \
      --expected-head RETAINED_REGISTRY_SHA256 \
      --expected-checkpoint RETAINED_LATEST_CHECKPOINT_SHA256

Inspection checks the entire local history, header marker, table
schema, sequence, predecessor links, hashes and external current
triple. It does not recheck historic Ed25519 signature inputs
unless the operator reruns Stage 263M with those original files.

## What still cannot be proved

This registry is NOT a remote independent append-only consensus
service, a TPM monotonic counter or an immutable witness log.
Attackers who can roll back BOTH registry and external current
triple can present an old, internally valid history. The Stage 263M
replay-journal verification and Stage 263N registry commit are in
TWO DISTINCT local SQLite databases and are NOT cross-DB atomic.

A privileged attacker may modify the replay journal after signature
verification. The program cannot prove different physical signer
machines, complete OS writer revocation, authentic execution of
observer tools, or complete discovery of alternate services.

All reports explicitly retain:
external_latest_registry_escrow_proved=false,
durable_hardware_rollback_prevention_proved=false,
global_writer_revocation_proved=false,
witness_fence_retirement_authorized=false,
witness_fence_retired=false.

The 17 synthetic regressions cover duplicate, stale, malicious,
concurrent and corrupted submissions, not a production PlayStation
or Nintendo Switch game build. PR remains Draft.
