# Stage 264I — signed receipt contradiction and repeated challenge evidence

Stage 264H authenticates two separately signed operator-inspection receipts
against independently provided current receipt hashes, challenges, receipt
sequence floors, and two fully verified local copies of the Stage 264E archive.

That check does **not** keep an independent history of all consumed
challenges or prove an operator never signed a different statement for the
same challenge. Stage 264I adds an **offline incident detector** for two
separately preserved, exact-byte pinned Stage 264H receipts **issued by the
same enrolled signer**:

    tools/audit_record_witness_publication_receipt_challenge_conflict.py

It verifies both complete Ed25519 signed receipt envelopes with the same
externally enrolled operator public PEM and independent exact-envelope
SHA-256 values. The enrolled scope, operator role and ID, 128-bit nonce,
individual audit IDs, predecessor receipt hashes, and receipt sequences are
supplied separately and must match each signed body exactly.

Every receipt must have an exact known schema and the mandatory flags:
\`copy_inspection_performed=true\`,
\`external_physical_custody_proved=false\`, and
\`witness_fence_retirement_authorized=false\`.
Signature verification and canonical body reconstruction reject tampering,
arbitrary extra fields, booleans masquerading as sequence numbers, wrong
public keys, scope impersonation and illicit fence/custody assertions.

## Two explicitly different incidents

The verifier reports one of two **cryptographically authenticated** incidents:

- \`conflicting_same_predecessor_claims\`: both signed receipts have the
  same challenge, audit ID, sequence number and predecessor receipt digest,
  but disagree in **storage identity, exact archive SHA-256 or evidence
  SHA-256**. These are materially different claims for the same receipt
  slot. Both have authentic signatures by one enrolled key.
- \`cross_context_nonce_reuse\`: one enrolled signer signs two different
  receipts with the same 128-bit challenge, but different authenticated
  audit IDs, sequences or predecessor receipt digests. This is evidence of
  repeated nonce **in two signed claims**, not evidence about who generated
  the nonce, which event was the latest or whether actual network replay
  happened.

Merely supplying the **same signed receipt twice** is *not* proof that a
second issuance happened. Different envelope hashes alone without differing
authenticated claims are likewise insufficient to prove a contradictory
archive/custody statement. The incident detector fails closed in these cases.

Its \`canonical_incident_sha256\` is domain-separated and independent of
which of the two receipts was listed first. Optionally an out-of-band
\`--expected-incident-sha256\` can constrain it to a separately retained
incident digest. This tool proposes that digest; it does **not** upload,
save, notarize or independently retain incident evidence.

## Read-only example

    python3 -m tools.audit_record_witness_publication_receipt_challenge_conflict \
      /private/receipt-first.json \
      /private/receipt-second.json \
      --scope private-wild-arms-publication-mirrors \
      --role operator-a \
      --operator-id enrolled-operator-a \
      --nonce SAME_INDEPENDENTLY_RETAINED_32_HEX_NONCE \
      --operator-public /enrolled/operator-a-public.pem \
      --operator-public-pin TRUSTED_OPERATOR_A_PUBLIC_PEM_SHA256 \
      --first-envelope-pin TRUSTED_FIRST_RECEIPT_SHA256 \
      --second-envelope-pin TRUSTED_SECOND_RECEIPT_SHA256 \
      --first-audit-id AUDIT_ID_ONE \
      --second-audit-id AUDIT_ID_TWO \
      --first-sequence FIRST_SEQUENCE \
      --second-sequence SECOND_SEQUENCE \
      --first-previous-sha256 TRUSTED_FIRST_PREDECESSOR_SHA256 \
      --second-previous-sha256 TRUSTED_SECOND_PREDECESSOR_SHA256

Exit 0 confirms two distinct authentic claims sharing the same supplied
challenge under the separately enrolled operator key. Exit 1 means the
supplied evidence does not establish either defined incident or fails
signature/enrollment validation. The JSON report contains only hashes,
booleans and bounded operator-neutral metadata; no signed envelope bytes,
private signing keys or archive copies.

## Limits

This verifier is strictly observational and does not contact or mutate any
keeper, archive, storage replica, or live authority. It does not enforce
nonce uniqueness **before signing**. That requires an independently
maintained monotonic nonce/receipt-consumption registry (or genuinely
remote service with durable CAS semantics and operator enrollment), which
is **not deployed** here. Signatures alone do not establish that challenges
were independently generated, that an operator acted honestly or that the
signed copy-inspection claims correspond to actual physical storage.

Two differently signed receipts can reflect separate service invocations,
simulated signatures or compromised signing keys. Their proof is about
authenticated *claims*, not the objective cause. Loss of the original
separately retained pins or signing keys compromises the trust assumptions.
No physical durability, independent off-host custody, globally newest head,
witness-fence release, Switch game-build, or emulator gameplay is proved.

All successful reports explicitly keep false:
\`source_challenge_freshness_proved\`,
\`actual_archive_custody_proved\`,
\`either_claim_was_stored_or_committed_proved\`,
\`external_nonce_uniqueness_registry_proved\`,
\`honest_operator_behavior_proved\`,
\`independently_retained_incident_digest_proved\`,
\`witness_fence_retirement_authorized\`,
\`witness_fence_retired\`,
\`automatic_cas_retry_authorized\`, and
\`native_switch_game_build_verified\`.
