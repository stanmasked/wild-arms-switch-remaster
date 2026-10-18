# Stage 263Y — dual-source strict signed-head advancement (research)

Stage 263X authenticates one challenge-bound HTTPS latest-head response against
the independently validated Stage 263W latest tuple. Stage 263Y
tools/audit_record_witness_publication_two_source.py compares **two**
independently enrolled authority responses and verifies strict progression
relative to **a complete previously signed pair**, whose domain-separated
SHA-256 was independently retained **outside BOTH authority servers**.

## Operation

Each source has its own canonical HTTPS URL (on a different DNS hostname),
authority ID, Ed25519 public key and externally retained exact PEM pin. Both
authority keys must be different from each other and from the two separately
pinned Stage 263W notary keys (four distinct DER key identities).

For the *old* generation, an independent operator retains both exact signed
Stage 263X envelopes, their distinct original 128-bit challenges, the expected
old Stage 263W tuple, and their exact signed authority sequence numbers. A
separate custodian-independent store retains the domain-separated checkpoint
SHA-256 computed by checkpoint_digest over the two full signed envelopes,
scope and both authority public-key pins. The old pair is authenticated again
in Stage 263Y, checked against the external SHA-256 and enrolled authority
pins; it is never enough to trust a self-declared or self-calculated digest.

For the *new* generation, the verifier must independently validate a **strict
Stage 263V / 263W transition** and supply the expected successor tuple. Stage
263Y requires new event_count > old count. It generates a fresh unpredictable
128-bit challenge **separately for each source**, checks no new challenge
duplicates any previous challenge, queries each external source over bounded,
CA-verified HTTPS, verifies both domain-separated Ed25519 signed responses,
and requires for BOTH sources:

- Matching enrolled URL, scope, identity and four-part Stage 263W head tuple
  plus complete notary-envelope bundle SHA-256.
- Source-specific authority sequence strictly greater than that source's
  prior externally pinned signed sequence.
- No witness-fence retirement authorization.

Either unreachable server, signature failure, mismatched tuple, rollback,
duplicate identity/challenge, invalid pin, rewritten signed old pair or
other inconsistency rejects the *whole* two-source comparison. No fallback to
a one-source quorum is allowed. The tool returns the SHA-256 of a proposed
successor pair of signed envelopes for independent out-of-band storage.

**It DOES NOT write that successor checkpoint to the external store.**
The receiving independent operator must persist and read back the new pin
with appropriate compare-and-swap / monotonic policy before making any
freshness claim. Even if an old pin was externally retained, the client cannot
prove it was the *globally newest* externally retained checkpoint.

## Example CLI

The example addresses are placeholders only; no remote production service
is deployed by this repository.

    python3 -m tools.audit_record_witness_publication_two_source \
      --source-a-url https://source-a.example.org/heads/current \
      --source-a-id independent-authority-a \
      --source-a-public /external/source-a.pem \
      --source-a-pin A_PUBLIC_PEM_SHA256 \
      --old-a-signed /external/old-a-signed.json \
      --old-a-challenge OLD_CHALLENGE_A_32_HEX \
      --old-a-sequence PREVIOUS_SEQUENCE_A \
      --source-b-url https://source-b.example.net/heads/current \
      --source-b-id independent-authority-b \
      --source-b-public /external/source-b.pem \
      --source-b-pin B_PUBLIC_PEM_SHA256 \
      --old-b-signed /external/old-b-signed.json \
      --old-b-challenge OLD_CHALLENGE_B_32_HEX \
      --old-b-sequence PREVIOUS_SEQUENCE_B \
      --notary-a-public /external/notary-a.pem \
      --notary-a-pin NOTARY_A_PUBLIC_PEM_SHA256 \
      --notary-b-public /external/notary-b.pem \
      --notary-b-pin NOTARY_B_PUBLIC_PEM_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --old-checkpoint-sha256 EXTERNALLY_RETAINED_SIGNED_PAIR_SHA256 \
      --old-count OLD_COUNT --old-head-sha256 OLD_HEAD \
      --old-history-sha256 OLD_HISTORY \
      --old-witness-sha256 OLD_WITNESS \
      --old-bundle-sha256 OLD_NOTARY_BUNDLE \
      --new-count NEW_COUNT --new-head-sha256 NEW_HEAD \
      --new-history-sha256 NEW_HISTORY \
      --new-witness-sha256 NEW_WITNESS \
      --new-bundle-sha256 NEW_NOTARY_BUNDLE

Exit code 0 is valid cryptographic comparison, 1 is conflict, 2 is
unavailable remote source. All reports remain redacted and explicitly
disallow custody/witness releases.

## Limits and trusted boundary

Distinct hostnames, signatures and DER keys are **not** proof that sources
have independent owners, machines, infrastructure, clocks, backing data or
administrators. If both source signing keys are compromised they can freshly
sign a coordinated false head (if the operator also provides matching
expected pins). Two consecutive valid pairs are NOT a global append-only
witness by themselves. Stage 263Y does not rerun Stage 263V's signed archive
prefix proof, nor Stage 263W's full old/new source validation; callers must
perform those separately. Merely presenting a prior externally pinned file
does not prove its pin is newest or rollback-resistant. An honest remote
source might legitimately be unavailable. The client has neither a remote
write/CAS API nor a durable independent monotonic counter.

The flags external_store_commit_or_readback_proved,
physical_or_administrative_independence_proved, global_latest_head_proved,
compromised_both_sources_rollback_excluded,
full_stage_263v_transition_rechecked_here, witness_fence_retirement_authorized,
witness_fence_retired, and native_switch_game_build_verified always remain
false. Automated release of an uncommitted or indeterminate witness fence is
FORBIDDEN; these tools add observation only, not custody mutation.

All tests use temporary Ed25519 keys and simulated HTTPS sources.
They are not live external attestation or Nintendo Switch gameplay tests.
