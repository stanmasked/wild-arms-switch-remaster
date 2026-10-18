# Stage 264A — reconciliation after indeterminate checkpoint CAS

Stage 263Z conditionally appends one local SQLite checkpoint event, commits,
then rereads through a different connection. Loss of an acknowledgment,
termination, disk errors or a concurrent writer can make the outcome unknown
to the calling process. Reissuing the same write blindly is forbidden.

Stage 264A provides a **read-only** observer in
tools/audit_record_witness_publication_cas_reconciliation.py.
It never calls the Stage 263Z advance function, mutates custody, or releases
a witness fence. It is a reference, NOT an independently operated remote
service.

## Trusted evidence required

Operators provide the complete original Stage 263Y report and its independently
authenticated, retained exact-byte SHA-256; the originally trusted prior
generation, signed-pair SHA-256 and chain event head; enrolled scope and
private reference keeper DB. The Stage 263V/W/Y evidence must have been
verified separately. Hashing a report supplied by the potentially compromised
local keeper is not a trustworthy external enrollment.

The observer checks the report schema and safety flags, opens the keeper
read-only and audits its full bounded hash chain and singleton head inside
a SQLite read transaction. A second independent read transaction must
produce exactly the same rows and head. If the state changes between reads,
the result is indeterminate and the tool fails closed.

It recomputes the exact attempted Stage 263Z event hash from the trusted
previous checkpoint, proposed new signed-pair pin, report hash, event count
and both authority sequence numbers. It authenticates the expected prior
event's exact presence in the locally audited chain.

Three possible observations:

- old_head_observed: the head still matches the externally provided old
  checkpoint. This does NOT prove no transaction is still in progress.
- candidate_commit_observed: the exact proposed next event is currently
  the chain head. This does NOT prove the acknowledgment was retained.
- candidate_superseded: the proposed event is an exact historical prefix,
  but the keeper has already advanced again. Trust the new head only after
  a fresh independently authenticated checkpoint.

Any different candidate event, truncated or modified chain, missing trusted
old event, scope mismatch, stale external pins, duplicate report keys or
unavailable DB is rejected. Observations never automatically retry an
ambiguous CAS request.

## CLI

    python3 -m tools.audit_record_witness_publication_cas_reconciliation \
      /operator-private/checkpoints.db \
      --report-file /operator-private/verified-stage-y-report.json \
      --independent-report-pin TRUSTED_STAGE_Y_REPORT_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --expected-generation TRUSTED_OLD_GENERATION \
      --expected-pair-pin TRUSTED_OLD_SIGNED_PAIR_SHA256 \
      --expected-event-head TRUSTED_OLD_CHAIN_EVENT_SHA256

A valid read-only observation exits 0. Conflicting or insufficient input
exits 1 without a success claim. All reports retain
automatic_retry_authorized=false,
external_operator_acknowledgment_proved=false,
externally_retained_latest_pin_proved=false,
physical_durability_proved=false,
global_latest_head_proved=false,
witness_fence_retirement_authorized=false,
witness_fence_retired=false and native_switch_game_build_verified=false.

## Security boundary

Two snapshots of one local SQLite DB cannot establish external physical or
administrative independence. A rollback of the DB alongside compromised
old external pins can still deceive the observer. Any subsequent concurrent
writer can invalidate an observed head immediately. The reference checker
does not implement trusted remote storage, TPM counters, durable external
readback, a real PS1 runtime or Nintendo Switch gameplay testing.
Never infer that the current latest checkpoint is safe from stale replay
without an independently authenticated monotonic source.

Synthetic CI covers precommit states, lost postcommit acknowledgment, later
advancement, corruption, changed snapshots and explicit no-retry behavior.
