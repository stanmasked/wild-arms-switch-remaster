# Stage 263X — live independent publication-head source (research only)

Stage 263W verifies the full signed publication-history transition against separately supplied current-head pins, but cannot establish that the external pins are latest. Stage 263X adds the read-only tool tools/audit_record_witness_publication_live_source.py to request a live challenge-bound signed head from an independently operated HTTPS authority.

## Required operator enrollment

The independent operator, outside custody and shared rollback control, must provision:
- An exact HTTPS URL on port 443 with a valid TLS certificate, and no redirect, proxy or client credentials.
- A distinct Ed25519 authority key with separately pinned PEM SHA-256 and enrolled authority ID; the authority DER key must differ from both separately pinned Stage 263W notary DER keys.
- An independently retained lower bound on the authority's monotonic sequence number.
- Trusted Stage 263W current event count, head SHA-256, signed history SHA-256, witness SHA-256 and complete signed notary bundle digest. These must come from a verified full Stage 263W transition, not a custody host assertion.

The read-only client generates a fresh random 128-bit nonce and sends an uncached HTTPS POST with the canonical request schema wild-arms-ps1-live-publication-head-request-v1, checkpoint_scope and challenge_nonce. No redirects or proxies are allowed. The CA-verified TLS connection alone is not sufficient.

The authority responds with an Ed25519 envelope using the repository's established three-field format (schema, body, signature_hex), context domain wild-arms-ps1-live-publication-head-source-v1 (followed by a null byte). The exact signed body fields are:

    schema = wild-arms-ps1-live-publication-head-source-v1
    source_url = exact enrolled HTTPS URL
    authority_id = enrolled authority identity
    checkpoint_scope = Stage 263W scope
    challenge_nonce = freshly issued request nonce
    authority_sequence = nonnegative integer >= external sequence floor
    event_count = independently verified Stage 263W count
    head_sha256 = independently verified Stage 263W journal head
    history_sha256 = independently verified Stage 263W full archive SHA-256
    latest_witness_sha256 = independently verified Stage 263W witness digest
    notary_bundle_sha256 = independently verified Stage 263W bundle digest
    witness_fence_retirement_authorized = false

The client requires exactly these fields, a valid Ed25519 signature under a pinned public key, correct scope, URL, authority, nonce, latest tuple and floor. It rejects unavailable/non-200 sources, redirect attempts, oversized or malformed responses, swapped keys, bad signatures, stale states or replays with a different nonce.

## Example invocation

This URL is only an illustrative endpoint; no actual authority is deployed by the repository.

    python3 -m tools.audit_record_witness_publication_live_source \
      --source-url https://independent.example.org/heads/current \
      --source-public /external/authority.pem \
      --source-public-pin AUTHORITY_PEM_SHA256 \
      --authority-id external-head-authority \
      --notary-a-public /external/notary-a.pem \
      --notary-a-public-pin NOTARY_A_PEM_SHA256 \
      --notary-b-public /external/notary-b.pem \
      --notary-b-public-pin NOTARY_B_PEM_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --external-minimum-sequence EXTERNAL_SEQUENCE_FLOOR \
      --expected-count TRUSTED_STAGE_263W_COUNT \
      --expected-head TRUSTED_STAGE_263W_HEAD_SHA256 \
      --expected-history-sha256 TRUSTED_STAGE_263W_HISTORY_SHA256 \
      --expected-witness-sha256 TRUSTED_STAGE_263W_WITNESS_SHA256 \
      --expected-notary-bundle-sha256 TRUSTED_STAGE_263W_NOTARY_BUNDLE_SHA256

Return code 0 means one authenticated matching live response; 1 means invalid/untrusted response; 2 means the independent source is unavailable. Reports are redacted, with no raw signed envelope or private nonce.

## Trust boundary

Actual external service provisioning, physical independence, real latestness, durable external floor and uninterrupted availability are NOT verified. A compromised authority can freshly sign a rolled-back state; a colluding operator can supply old Stage 263W external pins. The sequence check is relative only to an externally supplied lower bound and does not prove a global counter. This tool does not rerun Stage 263W; invoke both checks on their own evidence, with independently managed expected values. An observed live response does not prove the upstream service is honest or that its backing store is rollback-resistant.

Every successful report keeps independent_head_service_really_deployed_proved, remote_global_latest_head_proved, external_sequence_floor_independently_stored_proved, authority_honestly_reports_latest_proved, continuous_availability_proved, witness_fence_retirement_authorized, witness_fence_retired, and native_switch_game_build_verified false.

The tests use temporary Ed25519 keys and mocked HTTPS: they do not constitute a production remote source or a Nintendo Switch game test.
