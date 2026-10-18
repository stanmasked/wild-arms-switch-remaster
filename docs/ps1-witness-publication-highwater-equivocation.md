# Stage 264E — cryptographic evidence of contradictory sibling successors

The Stage 264D verifier accepts one co-signed checkpoint transition
conditioned on a local keeper and independently supplied current state. Two
mutually contradictory signed successors of *the same parent* cannot both
be the unique successor in one linear SQLite keeper. A detection process
therefore must validate both signed submissions **offline**, without
requiring the local keeper to have committed either branch.

Stage 264E adds a read-only offline verifier:
tools/audit_record_witness_publication_highwater_equivocation.py.

It accepts two distinct proposed Stage 264D bundles. Each bundle consists
of six full signed Ed25519 envelopes: two old Stage 264C operator checkpoint
certificates, two new operator checkpoint certificates, and two operator
transition endorsements. Every envelope is separately SHA-256-pinned
outside the source or custody host. Exact PEM key SHA-256 pins of the two
operators are also supplied independently, and DER key identities must be
different.

The verifier checks:

- Both bundles contain the **exact same** old operator envelopes, individually
  pinned to independently enrolled parent SHA-256 values.
- Both operator certificates in each branch agree on the old and new
  checkpoint generations, pair digests, event-chain head digests, event
  counts and both signed source sequences.
- Both bundles' successor generation equals old generation + 1. Event
  count and source sequences strictly advance, new pair and event digests
  differ from their own parent, and operator seal sequences increase.
- The complete endorsement of each operator cryptographically binds the
  exact old and new certificates **of its own branch**, the same scope,
  same previous transition-bundle SHA-256 and exact old/new checkpoint.
- The two authenticated siblings refer to the **same prior independent
  checkpoint** but disagree on BOTH next signed pair SHA-256 and next
  event-head SHA-256 at the same immediate successor generation.

The verifier computes an order-independent, domain-separated
canonical_evidence_sha256 over the parent enrollment and the two distinct
Stage 264D successor bundle identities and checkpoint states. Supplying an
independently retained expected evidence hash adds exact-match checking.
The canonical digest is *proposed*, not automatically stored or published.

No keeper database is read, reset, modified or considered authoritative
for this offline signature conflict. An operator may retain all twelve
raw signed envelopes privately, plus their pins, to reproduce verification
later. The stdout report includes only hashes, booleans and numeric
generations, not raw signatures or secrets.

## CLI

    python3 -m tools.audit_record_witness_publication_highwater_equivocation \
      --scope private-wild-arms-publication-mirrors \
      --operator-a-id offhost-highwater-a \
      --operator-a-public /private/observer-a.pem \
      --operator-a-pin ENROLLED_OPERATOR_A_PUBLIC_SHA256 \
      --operator-b-id offhost-highwater-b \
      --operator-b-public /private/observer-b.pem \
      --operator-b-pin ENROLLED_OPERATOR_B_PUBLIC_SHA256 \
      --parent-old-a-sha256 TRUSTED_PARENT_A_CERT_SHA256 \
      --parent-old-b-sha256 TRUSTED_PARENT_B_CERT_SHA256 \
      --previous-transition-bundle-sha256 TRUSTED_PARENT_TRANSITION_SHA256 \
      --expected-parent-generation PREVIOUS_GENERATION \
      --expected-parent-pair-pin PREVIOUS_SIGNED_PAIR_SHA256 \
      --expected-parent-event-head PREVIOUS_CHAIN_EVENT_SHA256 \
      --left-old-a /private/left/old-a.json \
      --left-old-a-sha256 LEFT_OLD_A_SHA256 \
      --left-old-b /private/left/old-b.json \
      --left-old-b-sha256 LEFT_OLD_B_SHA256 \
      --left-new-a /private/left/new-a.json \
      --left-new-a-sha256 LEFT_NEW_A_SHA256 \
      --left-new-b /private/left/new-b.json \
      --left-new-b-sha256 LEFT_NEW_B_SHA256 \
      --left-endorsement-a /private/left/endorse-a.json \
      --left-endorsement-a-sha256 LEFT_ENDORSE_A_SHA256 \
      --left-endorsement-b /private/left/endorse-b.json \
      --left-endorsement-b-sha256 LEFT_ENDORSE_B_SHA256 \
      --right-old-a /private/right/old-a.json \
      --right-old-a-sha256 RIGHT_OLD_A_SHA256 \
      --right-old-b /private/right/old-b.json \
      --right-old-b-sha256 RIGHT_OLD_B_SHA256 \
      --right-new-a /private/right/new-a.json \
      --right-new-a-sha256 RIGHT_NEW_A_SHA256 \
      --right-new-b /private/right/new-b.json \
      --right-new-b-sha256 RIGHT_NEW_B_SHA256 \
      --right-endorsement-a /private/right/endorse-a.json \
      --right-endorsement-a-sha256 RIGHT_ENDORSE_A_SHA256 \
      --right-endorsement-b /private/right/endorse-b.json \
      --right-endorsement-b-sha256 RIGHT_ENDORSE_B_SHA256

The optional --externally-pinned-evidence-sha256 checks a previously retained
evidence hash. Exit status 0 indicates two verified contradictory signed
claims, **not** authorization to choose a winner. Status 1 rejects invalid
or non-contradictory evidence.

## Limits / non-claims

This verifies contradiction in **signed claims**. It does not prove either
successor was actually accepted or durably committed in SQLite, that the two
operator keys are controlled by independent parties, that either claim is
the globally latest published head, or that the operator was honest.
Two signatures made by jointly compromised operators can both verify.
Source authority truthfulness and full Stage 263V/W history validation
remain separate prerequisites.

An older lineage may be replayed with authentic old independent pins;
only actual separately retained latest enrollment prevents that.
The checker never contacts real online source servers and never retires a
witness fence. There is no production fork alert, external transparency
log, operator service, independent CAS or Switch game build in this stage.

Every success report keeps these assertions false:
either_successor_was_committed_to_keeper_proved,
real_independent_operator_custody_proved,
externally_archived_evidence_proved,
global_latest_head_proved,
automatic_cas_retry_authorized,
witness_fence_retirement_authorized,
witness_fence_retired,
native_switch_game_build_verified.
