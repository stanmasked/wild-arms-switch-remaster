# Stage 264L — detached, locally retained complete nonce-fork evidence

Stage 264K compares two independently pinned Stage 264J SQLite nonce
registries. Its redacted report tells an operator if the histories agree,
one lags as a strict prefix, or they are irreconcilably forked, but it does
not preserve the raw independently audited events. The original databases
could subsequently be deleted or rolled back.

Stage 264L adds the reference utility

    tools/audit_record_witness_publication_receipt_nonce_divergence_evidence.py

It saves a complete bounded **private** evidence snapshot of two
*individually valid but incompatible* Stage 264J nonce event histories.
The artifact includes both full event rows (including nonce values and
signed receipt SHA-256), both operator enrollments, the expected scope,
two independently supplied genesis SHA-256 values and two independently
supplied current event-chain heads. This is sensitive operator evidence;
do not publish it in the public GitHub repository.

## Create-only flow

\`create\` requires private original SQLite files, in different 0700
directories, with owner-owned private 0600 file inodes; separately trusted
current head/genesis values for each. It performs two full read-only Stage
264K history inspections, checking identity and equality across the rounds.
Then it reconstructs **both** event chains in two fresh SQLite in-memory
databases and runs the original Stage 264J replay auditor on each, verifying
the complete external enrollment and final event heads. Creation is refused
unless both individually valid histories demonstrably differ.

Evidence is serialized as unique-key canonical JSON (maximum 4 MiB),
exclusively created with O_EXCL in a private destination directory,
fsynced and reopened to rerun detached history verification. Existing
or partially written artifacts are NEVER overwritten or silently retried.
The returned exact-byte \`archive_sha256\` is a proposed trust pin that
must be independently retained by the reviewing operator.

    python3 -m tools.audit_record_witness_publication_receipt_nonce_divergence_evidence \
      create /private-operator/incident-0001.json \
      --primary-registry /operator-a/private/nonce.db \
      --secondary-registry /operator-b/private/nonce.db \
      --scope private-wild-arms-publication-mirrors \
      --primary-genesis-pin TRUSTED_A_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_GENESIS_SHA256 \
      --primary-head-pin TRUSTED_A_LATEST_HEAD_SHA256 \
      --secondary-head-pin TRUSTED_B_LATEST_HEAD_SHA256

It returns a *diagnosis*, not an instruction to merge:

- \`strict_prefix_lag\`: one authentic chain is an exact prefix of another.
- \`forked_hash_chains\`: two individually valid event chains have
  contradictory event rows. An additional boolean detects the same nonce
  appearing in different reservation claims across branches.

## Independent detached verification

\`inspect\` does not need either original registry. It takes the saved
private canonical evidence artifact and REQUIRES its separately retained
exact-byte SHA-256, plus the two separately retained genesis/head SHA-256
values and the scope:

    python3 -m tools.audit_record_witness_publication_receipt_nonce_divergence_evidence \
      inspect /private-operator/incident-0001.json \
      --archive-pin INDEPENDENT_ARCHIVE_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --primary-genesis-pin TRUSTED_A_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_GENESIS_SHA256 \
      --primary-head-pin TRUSTED_A_LATEST_HEAD_SHA256 \
      --secondary-head-pin TRUSTED_B_LATEST_HEAD_SHA256

The verifier checks file ownership and private permissions, rejects
symlinks/hardlinks, oversized, truncated, duplicate-field or noncanonical
JSON, replays every event into independent **memory-only** SQLite contexts,
and checks both chained heads against *the caller's external trust pins*.
The archive file is never modified. The CLI report intentionally includes
only SHA-256 digests, event counts, conflict class and booleans; it never
prints raw nonces, private keys, archive payload or signed receipt envelopes.

A loss of the original databases does not prevent inspection of the
complete archived events. However, deleting the evidence archive itself
cannot be prevented by a normal local filesystem. A separately retained
exact-byte SHA-256 can detect alteration/loss, not recover it.

## Security / project limits

These are **locally created unsigned** private evidence files, not signed
off-host custody receipts. Correct event hash chains do not authenticate
the physical identities of operators or establish actual independent
retention of the separately passed hashes. A malicious operator who can
replace both event histories *and* the independently trusted head pins
can produce a different internally consistent proof.

The archive does not prove which fork is current or authoritative, whether
an actual network replay occurred, whether an independently administered
global nonce CAS exists, or that a signed receipt was physically delivered.
A read-only snapshot cannot guarantee future absence of fork or tampering.
No automatic merge, ambiguous-signature retry, custodian release, witness
fence retirement, Nintendo Switch game build or emulator gameplay is part
of this stage. All success reports explicitly retain those negative flags.
