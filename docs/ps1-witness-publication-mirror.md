# Stage 263R — comparison of separately pinned publication mirrors

This stage introduces `tools.audit_record_witness_publication_mirror`,
a **read-only** comparator for two private Stage 263Q SQLite journals.
The tool requires independently retained count and SHA-256 head for
**each** copy. It checks the entire chain, schema, integrity marker and
freeze state before comparing the ordered event commitments.

The copies must be different paths **and have different filesystem
(device, inode) identities**; a hard link does not qualify as a second
copy. This check cannot prove that two distinct inodes reside on
independent machines. A byte-identical event history
passes even when both journals contain a signed conflict and are frozen:
a frozen conflict cannot be erased or treated as authority to continue
publication. A shorter history is recognized as a stale prefix and
**fails closed**; divergence at any sequence is rejected even when both
local histories have internally valid signatures/commitments.

Use:

```sh
python3 -m tools.audit_record_witness_publication_mirror \
  /independent-a/publications.sqlite \
  /independent-b/publications.sqlite \
  --a-count OPERATOR_A_PINNED_COUNT \
  --a-head OPERATOR_A_PINNED_HEAD_SHA256 \
  --b-count OPERATOR_B_PINNED_COUNT \
  --b-head OPERATOR_B_PINNED_HEAD_SHA256
```

The tool neither copies nor repairs records, changes accepted history,
opens the witness database nor authorizes release of a stuck witness
fence. It accepts **only current snapshots as supplied**; the two
SQLite reads are not an atomic cross-host or cross-database operation.

**Trust limitation:** this prototype does not prove the two copies
reside on separate physical machines or have independent administrators.
A synchronized rollback of both copies and both external pins can still
appear consistent. Nor does it discover unsubmitted third archives or
verify the historical signed receipt bytes whose SHA-256 values were
recorded by Stage 263Q. A successful comparison always reports
`separate_physical_storage_proved=false`,
`externally_pinned_heads_are_latest_proved=false`,
`hidden_third_archive_excluded=false`,
`historical_rollback_with_old_pins_excluded=false` and
`witness_fence_retirement_authorized=false`.

The regression suite covers exact copies, valid diverging copies,
prefix copies, tampering, mistaken external pins and frozen conflict
retention. These synthetic tests do not attest production PlayStation
or Nintendo Switch execution.
