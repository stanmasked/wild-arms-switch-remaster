# Stage 263W — challenged latest signed publication head

Stage 263V proves that one signed archive strictly extends an older
archive, but two internally valid past snapshots can still be replayed.
Stage 263W adds a read-only two-notary Ed25519 statement about the
independently supplied CURRENT latest count, journal SHA-256, full
signed history SHA-256, and latest signed mirror-witness-pair SHA-256.

## Procedure

An independent verifier must issue a new unpredictable 128-bit hex
challenge nonce and obtain the trusted latest four-part tuple
OUTSIDE the custody host. Two separately controlled Ed25519 notaries
check that tuple and independently sign identical versioned bodies
created with the make_body function of
tools/audit_record_witness_publication_latest_head.py.
They sign the same old-to-new Stage 263V transition, scope and challenge
with distinct notary roles. Each signed body explicitly has
witness_fence_retirement_authorized=false.

The verifier takes both exact signed envelopes, distinct externally
pinned PEM SHA-256 public key identities, the original challenge and
an externally retained SHA-256 of the complete two-envelope notary
bundle. It also needs both Stage 263V old and new journal pairs,
signed archives, original witness public keys and independent exact
SHA-256 heads and archive digests.

Invocation:

    python3 -m tools.audit_record_witness_publication_latest_head       /old/a.sqlite /old/b.sqlite /old/signed-history.json       /new/a.sqlite /new/b.sqlite /new/signed-history.json       --old-count OLD_COUNT --old-head OLD_HEAD_SHA256       --old-history-sha256 OLD_HISTORY_SHA256       --old-latest-witness-sha256 OLD_SIGNED_WITNESS_SHA256       --new-count NEW_COUNT --new-head NEW_HEAD_SHA256       --new-history-sha256 NEW_HISTORY_SHA256       --new-latest-witness-sha256 NEW_SIGNED_WITNESS_SHA256       --witness-admin-a-public /keys/witness-a.pem       --witness-admin-a-public-pin WITNESS_A_PIN       --witness-admin-b-public /keys/witness-b.pem       --witness-admin-b-public-pin WITNESS_B_PIN       --notary-a-signed /notary-a/signed.json       --notary-a-public /notary-a/public.pem       --notary-a-public-pin NOTARY_A_PIN       --notary-b-signed /notary-b/signed.json       --notary-b-public /notary-b/public.pem       --notary-b-public-pin NOTARY_B_PIN       --scope private-wild-arms-publication-mirrors       --external-challenge-nonce FRESH_CHALLENGE_32_HEX       --external-latest-count TRUSTED_LATEST_COUNT       --external-latest-head TRUSTED_LATEST_HEAD_SHA256       --external-latest-history-sha256 TRUSTED_LATEST_HISTORY_SHA256       --external-latest-witness-sha256 TRUSTED_LATEST_WITNESS_SHA256       --external-notary-bundle-sha256 TRUSTED_NOTARY_BUNDLE_SHA256

The module first authenticates both role-specific Ed25519 statements,
checks independent DER public-key identities, scope, challenge and
separate exact external current tuple, and reruns the complete Stage
263V transition validation. It reports no private signing material
and has no write or witness-fence retirement actions.

## Critical trust boundary

This program does NOT query, publish to, or operate any real remote
latest-head archive. It cannot prove the challenge was independently
fresh, two notaries physically distinct, or the external latest head
actually current. An attacker with an older valid pair of snapshots,
old valid notary signatures, an old challenge AND old external pins
can still construct a passing verification. The verifier's role is
to reject old submissions relative to independently trustworthy
CURRENT pins, never to pretend that trust already exists.

Every successful result keeps the following flags false:
actual_external_challenge_freshness_proved,
trusted_current_external_pin_storage_proved,
old_pins_plus_old_challenge_replay_excluded,
global_monotonic_counter_proved,
independent_physical_notary_control_proved,
witness_fence_retirement_authorized,
witness_fence_retired,
native_switch_game_build_verified.

16 local synthetic regressions cover signature tampering, operator
collusion via same key, different signed heads, challenge replay,
externally retained head mismatch, complete transition validation
and no witness fence release. No PS1 gameplay or Switch build was
certified.
