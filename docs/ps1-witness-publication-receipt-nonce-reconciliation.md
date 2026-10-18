# Stage 264K — read-only two-registry nonce history reconciliation

Stage 264J enforces a single nonce space only for two operators sharing
one *local* SQLite ledger. If each operator independently maintains its own
registry, both registries can accept the same nonce or diverge after the
same signed predecessor. Stage 264K adds a **read-only diagnostic** for
that trust boundary, without pretending to deploy distributed CAS.

The new tool is:
\`tools/audit_record_witness_publication_receipt_nonce_reconciliation.py\`

It requires **two individually supplied latest event-chain SHA-256 pins**,
two individually supplied Stage 264J enrolled genesis SHA-256 pins and a
shared expected scope. Both registry copies must be owner-owned regular
0600 files in different owner-owned private 0700 parent directories,
with different inode identities and no symlinks or hardlinks.

For each of two audit rounds it:

- Opens both databases read-only, without creating a missing database.
- Replays each Stage 264J registry's entire bounded event hash chain,
  checks SQLite integrity, exact schema, two-operator enrollment and
  reservation/completion monotonicity, non-reused nonce and scope.
- Requires each observed latest event-head SHA-256 to match its
  **separately provided externally trusted pin** and each genesis hash
  to match the separately supplied genesis pin.
- Compares complete ordered event rows, not just row counts or the
  names of operator storage endpoints.
- Checks local file and parent inode identities before and after the
  audits, and rejects changed event histories across audit rounds.

A successful result means two **local** independently observed file paths
have exactly the same verified state, *conditional on the supplied external
pins*. No persistent state changes or automatic signing is performed.

If both histories are individually valid but disagree, the CLI exits 1
and reports a minimal conflict class:

- \`strict_prefix_lag\`: one complete audited history is an exact prefix
  of the other. It is NOT safe to merge or automatically advance either.
- \`forked_hash_chains\`: the histories differ at an event. The response
  includes the common verified event count. If the two branches also
  contain the same nonce as *different reservation claims*, a separate
  boolean indicates the cross-registry nonce collision. It never dumps
  the nonce bytes or signed receipt contents.

Other conflicts, including corrupted databases, wrong external hashes,
unsafe filesystem paths, changed enrollment, absent files or inode swaps,
return the generic \`untrusted\` conflict class, with no automatic recovery.

Example:

    python3 -m tools.audit_record_witness_publication_receipt_nonce_reconciliation \
      /operator-a/private/receipt-nonces.db \
      /operator-b/private/receipt-nonces.db \
      --primary-head-pin INDEPENDENTLY_RETAINED_A_LATEST_HEAD_SHA256 \
      --secondary-head-pin INDEPENDENTLY_RETAINED_B_LATEST_HEAD_SHA256 \
      --primary-genesis-pin ENROLLED_A_GENESIS_SHA256 \
      --secondary-genesis-pin ENROLLED_B_GENESIS_SHA256 \
      --scope private-wild-arms-publication-mirrors

**Limits.** Two directories are not physical or administrative
independence. Equal local database bytes and separately supplied hex
strings do not prove independent custody of the strings. The check
cannot prevent another host from consuming a nonce at the same time,
cannot establish which fork is authoritative or prove a globally latest
ledger, and cannot repair uncertain receipts. It is **not** a distributed
consensus algorithm or durable off-host CAS service.

The reference program never changes either registry, never resolves
forks or releases witness fences, never retries ambiguous signing, and
does not build or test Nintendo Switch gameplay. Success reports
explicitly keep false:

\`offhost_admin_independence_proved\`,
\`independent_external_head_persistence_proved\`,
\`global_nonce_cas_consensus_proved\`,
\`registry_durability_proved\`,
\`automatic_ledger_merge_authorized\`,
\`automatic_cas_retry_authorized\`,
\`witness_fence_retirement_authorized\`,
\`witness_fence_retired\`, and
\`native_switch_game_build_verified\`.
