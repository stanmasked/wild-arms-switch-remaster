# Stage 264O — pre-sign Ed25519 attestation challenge reservation

Stage 264N can show **after the fact** that one enrolled operator signed two
conflicting Stage 264M fork-archive inspection attestations or reused one
challenge in two attestation slots. Stage 264O adds an atomic *local* guard
to the Stage 264M operator-side **CLI signing path**:

- \`tools/audit_record_witness_publication_attestation_nonce_guard.py\`
- \`tools/audit_record_witness_publication_nonce_divergence_attestations.py\`

The \`sign\` CLI now **requires** \`--attestation-registry\`,
\`--expected-registry-head\` and \`--storage-id\`. Missing arguments cause a
redacted fail-closed response, not fallback to the unguarded signer. The
previous \`verify\` CLI remains a read-only check without a nonce registry.

Use a **separate** enrolled, private Stage 264J nonce-ledger database for
fork-archive attestations; do not share the registry with Stage 264H
ordinary evidence-copy receipts. The original Stage 264J initialization
and snapshot interface provide:

- exactly two distinct operator IDs, storage IDs and enrolled public PEM
  hashes under one attestation-scope genesis SHA-256;
- a create-only owner-private 0600 SQLite file in a 0700 directory;
- independently retained genesis and **current event-head SHA-256** trust
  pins and strict replay of the full hash-chained history;
- SQLite \`BEGIN IMMEDIATE\` to exclude simultaneous local reservations.

To initialize, invoke the Stage 264J \`init\` command with the full two-role
enrollment and externally precomputed genesis pin:

    python3 -m tools.audit_record_witness_publication_receipt_nonce_ledger \
      init /private/attestation-nonces.db \
      --scope private-wild-arms-publication-mirrors \
      --expected-genesis-pin TRUSTED_ATTESTATION_GENESIS_SHA256 \
      --operator-a-id fork-witness-operator-a \
      --storage-a-id fork-inspection-storage-a \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-a-pin TRUSTED_OPERATOR_A_PEM_SHA256 \
      --operator-a-initial-previous-sha256 TRUSTED_A_PREVIOUS_ATTESTATION_SHA256 \
      --operator-b-id fork-witness-operator-b \
      --storage-b-id fork-inspection-storage-b \
      --operator-b-public /enrolled/operator-b.pem \
      --operator-b-pin TRUSTED_OPERATOR_B_PEM_SHA256 \
      --operator-b-initial-previous-sha256 TRUSTED_B_PREVIOUS_ATTESTATION_SHA256

Example Stage 264M signing command now requires the extra guard options:

    python3 -m tools.audit_record_witness_publication_nonce_divergence_attestations \
      sign /private/incident-0001.json \
      --scope private-wild-arms-publication-mirrors \
      --audit-id audit-incident-001 \
      --archive-pin TRUSTED_ARCHIVE_SHA256 \
      --primary-genesis-pin TRUSTED_A_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_GENESIS_SHA256 \
      --primary-head-pin TRUSTED_A_HEAD_SHA256 \
      --secondary-head-pin TRUSTED_B_HEAD_SHA256 \
      --role operator-a --operator-id fork-witness-operator-a \
      --challenge FRESH_INDEPENDENT_32_HEX_NONCE \
      --sequence NEXT_A_SEQUENCE \
      --previous-attestation-pin TRUSTED_PREVIOUS_ATTESTATION_SHA256 \
      --signing-private /operator-private/key-a.pem \
      --signing-public /enrolled/operator-a.pem \
      --signing-public-pin TRUSTED_OPERATOR_A_PEM_SHA256 \
      --output /operator-private/signed-attestation-a.json \
      --attestation-registry /private/attestation-nonces.db \
      --expected-registry-head TRUSTED_CURRENT_REGISTRY_HEAD_SHA256 \
      --storage-id fork-inspection-storage-a

## Signing safety protocol

The Stage 264O guard:

1. Checks the enrolled public PEM SHA-256 and replays the full private
   Stage 264L evidence archive against independently supplied pins.
2. Builds the exact expected Stage 264M signed body; computes a
   **domain-separated SHA-256 of every canonical field** (including
   audit identity, archive SHA-256, both registry genesis/head hashes,
   nonce, sequence, previous attestation and no-release flags).
3. Under a single SQLite \`BEGIN IMMEDIATE\` transaction, checks the
   independently supplied latest nonce-ledger event head, registered
   role/operator/storage/public PEM pin, **globally unused nonce** and
   strictly next per-role sequence and preceding signed attestation SHA-256.
   Then commits a hash-chained \`reserve\` event with the canonical body
   commitment *before any Ed25519 signature is attempted*.
4. Runs the existing Stage 264M signed attestation generator, independently
   reopens the complete envelope, checks its Ed25519 signature, compares its
   body to the reserved body, and appends a hash-chained \`complete\` event
   with the exact signed envelope SHA-256. The updated ledger head is
   returned for **independent external retention** by the operator.

If signing fails, filesystem persistence is ambiguous, receipt verification
fails, or the completion transaction is interrupted, the challenge stays
**pending**. It cannot be automatically cleared, retried, reissued or
assigned to another role using the same local registry. A different
unused challenge for the **same** operator is also blocked while pending.
There is NO automatic cleanup or recovery path.

## Limits

The on-disk database is local; it does **not** prove globally unique nonces
across two physically separate computers running separate registries, or
that the latest returned head SHA-256 is actually retained outside the
operator host. The guard checks caller-supplied external trust anchors but
cannot authenticate their real provenance.

The Stage 264M low-level Python \`attest(...)\` function remains directly
callable, and anyone holding the signing private key can bypass this
software-enforced CLI path. Distinct Ed25519 keys do not prove independent
human operators, physical custody, globally latest head or honest signers.
A local database and filesystem cannot guarantee off-host durability.

No automatic nonce recovery, merging of contradictory histories, custodian
mutation, witness-fence release, Nintendo Switch game build or emulator
gameplay is performed. A successful result keeps all corresponding
independence/recovery/release claims explicitly false.
