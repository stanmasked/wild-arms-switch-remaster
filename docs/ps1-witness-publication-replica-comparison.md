# Stage 263R — independently pinned publication-replica comparison

Stage 263Q records Ed25519-signed operator receipt publications and
the first observed conflicting signed publication in a private local
SQLite journal. The local writer cannot guarantee that an operator
has published or retained a replica elsewhere.

Stage 263R adds a **read-only** comparison of two distinct physical
SQLite file identities. Each is checked with Stage 263Q's full schema,
head-chain and conflict audit, and against its own *independently
retained* exact event count and current head SHA-256.

The comparison also requires a **third historical floor** (event
count, event SHA-256) independently retained before the current
comparison. Both histories MUST still contain that exact anchored
event. An attacker can restore both current copies and their old
"latest" pins, but if the independently retained floor is newer
than that rollback, verification fails.

## Invocation

```sh
python3 -m tools.audit_record_witness_publication_replica_compare \
  /private-operator-a/escrow-publications.sqlite \
  /private-operator-b/escrow-publications.sqlite \
  --a-count OPERATOR_A_RETAINED_COUNT \
  --a-head OPERATOR_A_RETAINED_HEAD_SHA256 \
  --b-count OPERATOR_B_RETAINED_COUNT \
  --b-head OPERATOR_B_RETAINED_HEAD_SHA256 \
  --floor-count SEPARATELY_RETAINED_HISTORICAL_COUNT \
  --floor-head SEPARATELY_RETAINED_HISTORICAL_SHA256
```

Store these seven external values outside both SQLite files. The
floor may be genesis (count=0), but for meaningful rollback
detection it should be a recent older accepted event count/head
from a **separate trusted channel**. Each operator should independently
authenticate their corresponding filesystem and source file.

Both paths must be existing private regular files in private
directories; symlinks and hard-linked aliases are rejected. Only
one signed-publication intake ledger per file is allowed.

Each SQLite snapshot is opened using `BEGIN IMMEDIATE` and audited
against the original Stage 263Q table schema and every complete
hash-linked event. Both file snapshots remain open while the full
histories are compared. No file, custody database or witness state
is changed.

**A successful result requires the entire ordered events to agree.**
Two equal final head strings are not sufficient without rechecking
all events. The tool rejects an independently pinned replica that
is behind another, a signed conflicting fork with different valid
event hashes, a wrong external head, an invalid floor, a corrupted
SQLite row, an unexpected SQL trigger/view/index, and any conflict
freeze present in either copy.

The CLI returns 0 only on verified matching histories with no
local conflict. It returns 1 for any detected mismatch or publication
integrity conflict, and 2 for invalid filesystem or runtime input.
It emits only a compact summary and a domain-separated comparison
digest; no private signed receipt bytes, signing keys, or process
arguments are exported.

## Residual risks

- This tool **does not deploy or contact a remote service**.
  Two input files are not proof of independent operators, independent
  physical media or correct externally retained pins.
- The two SQLite snapshots cannot be globally atomic with remote
  service activity. A privileged local attacker can change a
  journal immediately after the comparison.
- A local Stage 263Q hash chain stores SHA-256 commitments to signed
  receipts but does not itself retain their original complete bytes.
  To authenticate historical signatures, keep original signed
  envelopes and re-run prior Stage 263O/P verification.
- If attackers restore **both** old archives AND replace all the
  supposed independent current and floor pins, this comparison can
  pass the old history. Neither three operator signatures nor
  local SQLite hashes alone establish globally fresh state.
- Unknown replicas or hidden equivocations may remain undiscovered.
  No part of this comparison proves permanent Linux writer
  revocation or actual Nintendo Switch gameplay.

The success report explicitly includes false claims for
`independent_replica_operators_authenticated`,
`physical_storage_independence_proved`,
`all_hidden_forks_or_archives_discovered`,
`global_latest_tip_freshness_proved`,
`rollback_if_all_pins_substituted_excluded`,
`cross_host_snapshot_atomicity_proved`,
`witness_fence_retirement_authorized` and
`witness_fence_retired`.

Stage 263R includes 19 synthetic regression tests. No unresolved
witness fence is retired or negative outcome reconciled.
