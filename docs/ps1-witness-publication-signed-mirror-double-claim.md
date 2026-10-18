# Stage 264R — signed mirror acknowledgment contradictions and repeated challenges

Stage 264Q authenticates two enrolled Ed25519 operator acknowledgments
against full Stage 264P mirror-registry and signed-completion audits. The
pair binds one known checkpoint. It does not detect whether **one** key has
signed a second contradictory acknowledgment for the same prior position.

The Stage 264R reference checker
\`tools/audit_record_witness_publication_signed_mirror_double_claim.py\`
requires **two distinct**, complete Stage 264Q signed JSON envelopes from
the **same enrolled Ed25519 public key**, each with an independently
supplied exact-byte SHA-256, plus common expected scope/role/operator
identity/genesis hashes and separate expected audit IDs, 128-bit nonces,
sequences and previous signed acknowledgment digests.

It verifies both Ed25519 signatures and reconstructs every signed claim
field with the Stage 264Q canonical body, including the required false
external custody, automatic reconciliation and fence-retirement flags.

Two conditions can yield a domain-separated incident SHA-256:

- \`forked_same_predecessor_mirror_acknowledgments\`: distinct, genuine
  signed statements have the **same sequence number and previous
  acknowledgment SHA-256** but differ materially in signed claims
  (archive history heads, private signed completion manifest digest,
  signed audit ID, challenge, etc.).
- \`challenge_reused_across_mirror_acknowledgment_slots\`: the same
  expected verifier challenge was signed by one enrolled key in two
  **different sequence or predecessor slots**.

An identical signed statement presented twice is not a second issuance.
Two different statements using a new challenge at a new slot are not
an incident. The proposed \`canonical_incident_sha256\` is independent
of which envelope is presented first, and can be checked against an
independently supplied \`--expected-incident-sha256\`. This checker does
not persist or externally notarize the incident.

The read-only CLI needs no source SQLite registry files:

    python3 -m tools.audit_record_witness_publication_signed_mirror_double_claim \
      /private/mirror-ack-first.json /private/mirror-ack-second.json \
      --scope private-wild-arms-publication-mirrors \
      --role operator-a --operator-id registered-operator-a \
      --public /enrolled/operator-a.pem \
      --public-pin TRUSTED_A_PEM_SHA256 \
      --genesis-a TRUSTED_LEDGER_GENESIS_A_SHA256 \
      --genesis-b TRUSTED_LEDGER_GENESIS_B_SHA256 \
      --first-envelope-pin PINNED_SIGNED_FIRST_SHA256 \
      --second-envelope-pin PINNED_SIGNED_SECOND_SHA256 \
      --first-audit-id EXPECTED_FIRST_AUDIT_ID \
      --second-audit-id EXPECTED_SECOND_AUDIT_ID \
      --first-nonce EXPECTED_FIRST_32_HEX_NONCE \
      --second-nonce EXPECTED_SECOND_32_HEX_NONCE \
      --first-sequence EXPECTED_FIRST_SEQUENCE \
      --second-sequence EXPECTED_SECOND_SEQUENCE \
      --first-previous-sha256 EXPECTED_FIRST_PREDECESSOR_SHA256 \
      --second-previous-sha256 EXPECTED_SECOND_PREDECESSOR_SHA256

Exit 0 means the **signed statements** show one precisely defined
contradiction; exit 1 indicates untrusted/invalid/non-incident evidence.
The JSON output is redacted and does not expose nonce plaintext or signed
envelope contents. Every successful result explicitly keeps
\`either_underlying_sqlite_registry_audited_proved=false\`,
\`any_attested_manifest_envelopes_were_revalidated_proved=false\`,
\`actual_independent_physical_operator_custody_proved=false\`,
\`independent_challenge_freshness_proved=false\`,
\`externally_retained_incident_digest_proved=false\`,
\`global_attestation_nonce_cas_proved=false\` and all automatic merge,
retry, witness-fence retirement and native Switch build flags false.

**Trust boundaries:** this detector never opens the mirror registries or
the signed completion manifest. It does NOT establish that claimed audits
occurred, that a referenced SQLite history existed, which head was latest,
whether a nonce came from an independent verifier, whether a signer was
honest, or that two physical operators independently stored anything.
Compromised signing keys can generate authentic but false claims. A
signature proves only a statement by the enrolled key. No deployed
global monotonic nonce CAS, WORM, off-host custody service or gameplay
build is created by this stage.
