# Stage 264N — conflicting signed attestation slots and repeated challenges

Stage 264M creates separately pinned Ed25519 inspection statements by two
operator key identities about a fully replayed private Stage 264L archive.
That proves limited authenticated statements for one inspected artifact,
but does not by itself detect if **one operator** later signed an
inconsistent or repeated statement at the same predecessor/sequence.

Stage 264N adds read-only **offline incident detection**:

    tools/audit_record_witness_publication_nonce_attestation_double_claim.py

It authenticates TWO separately preserved, exact SHA-256-pinned, complete
Stage 264M Ed25519 envelopes under the **same** enrolled operator PEM key,
operator ID, role, scope and genesis pair. Caller-supplied trusted context
includes a separate expected audit ID, 128-bit nonce, sequence, previous
attestation SHA-256, archive SHA-256, and both head SHA-256 values for each
statement. Every field is reconstructed using the original Stage 264M
canonical attestation schema; unexpected fields, invented external custody,
automatic merge or witness-fence authorization are rejected.

Only two precisely defined incidents are considered evidence:

- **forked_same_predecessor_attestations**: same operator, same
  sequence and previous signed attestation hash, but two materially
  different signed bodies (archive/head/audit/challenge/description).
  One unmodified envelope repeated twice is NOT a second issuance.
- **challenge_reused_across_attestation_slots**: same enrolled operator
  signing key and same expected 128-bit challenge in two distinct
  predecessor or sequence slots. A new challenge at a new valid
  slot is not evidence of an incident.

For two verified claims, a domain-separated order-independent
\`canonical_incident_sha256\` is computed over the **authenticated bodies**,
not the signature bytes. A caller may constrain it with separately
retained \`--expected-incident-sha256\`. The digest is a proposed
evidence identifier, NOT proof that an independent third party
retained or witnessed the evidence.

Example (complete signed envelope paths should remain private):

    python3 -m tools.audit_record_witness_publication_nonce_attestation_double_claim \
      /private/operator/attestation-1.json \
      /private/operator/attestation-2.json \
      --scope private-wild-arms-publication-mirrors \
      --role operator-a \
      --operator-id fork-witness-operator-a \
      --public /enrolled/operator-a-public.pem \
      --public-pin TRUSTED_SIGNER_PEM_SHA256 \
      --genesis-a TRUSTED_A_GENESIS_SHA256 \
      --genesis-b TRUSTED_B_GENESIS_SHA256 \
      --first-envelope-pin TRUSTED_SIGNED_ENVELOPE_1_SHA256 \
      --second-envelope-pin TRUSTED_SIGNED_ENVELOPE_2_SHA256 \
      --first-audit-id ENROLLED_AUDIT_1 \
      --second-audit-id ENROLLED_AUDIT_2 \
      --first-nonce INDEPENDENT_32_HEX_CHALLENGE_1 \
      --second-nonce INDEPENDENT_32_HEX_CHALLENGE_2 \
      --first-sequence ENROLLED_SEQUENCE_1 \
      --second-sequence ENROLLED_SEQUENCE_2 \
      --first-previous-sha256 TRUSTED_PRIOR_1_SHA256 \
      --second-previous-sha256 TRUSTED_PRIOR_2_SHA256 \
      --first-archive-pin PINNED_ARCHIVE_1_SHA256 \
      --second-archive-pin PINNED_ARCHIVE_2_SHA256 \
      --first-head-a TRUSTED_FIRST_A_HEAD_SHA256 \
      --first-head-b TRUSTED_FIRST_B_HEAD_SHA256 \
      --second-head-a TRUSTED_SECOND_A_HEAD_SHA256 \
      --second-head-b TRUSTED_SECOND_B_HEAD_SHA256

Exit 0: two distinct authentic claims prove one of those two specific
incidents, conditional on caller-supplied enrolled pins. Exit 1: any
invalid, unauthenticated or non-incident evidence. Output is redacted
JSON with incident classification, digest and explicit negative security
claims; it never emits raw signed envelopes or nonce plaintext.

## Important limits

Unlike the Stage 264M complete archive inspection, this comparison
does **not** need the referenced Stage 264L archive bytes. That allows
forensic use after those archives are lost, but it also means that even
two valid Ed25519 signatures DO NOT prove either archive existed or was
successfully inspected. Signed body flags are operator claims, not
independent physical custody attestation.

Stage 264N detects, rather than prevents, double signing or challenge
reuse. No distributed monotonic signer-side sequence register, nonce
allocator, independent archive receipt custody, WORM, global latest
head, or operator honesty is established. Compromised keys can produce
two authentic but false claims. The original Stage 264M signer and
enrollment remain separately testable; no automatic retry, fork
selection, SQLite merge, witness-fence retirement or Nintendo Switch
gameplay modification is part of Stage 264N.
