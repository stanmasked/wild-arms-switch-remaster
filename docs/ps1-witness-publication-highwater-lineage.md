# Stage 264D — paired high-watermark transition endorsements

The Stage 264C two-operator historical floor proves that a complete local
keeper chain extends one externally pinned checkpoint when the latest
operator seals are really retained outside the custodian. It does **not**
by itself bind successive historical floor endorsements into an explicit
operator-by-operator transition.

Stage 264D adds a **read-only** verifier:

    tools/audit_record_witness_publication_highwater_lineage.py

It accepts six exact signed envelopes:

- Two **old** Stage 264C Ed25519 operator checkpoint certificates.
- Two **new** Stage 264C Ed25519 operator checkpoint certificates.
- Two Stage 264D Ed25519 transition endorsements (one from each operator).

The verifier demands independently retained SHA-256 pins for the exact bytes
of *all six envelopes* and independently pinned public PEMs of two different
operator DER key identities. It checks both old certificates agree on
scope, pair digest, chained-event head, generation, event count and authority
A/B sequences, and similarly checks the two new certificates agree. Each
operator's *new seal sequence* must strictly exceed their old sequence.
Generation, event count, both source sequences, signed pair digest and event
head must strictly progress.

Each transition endorsement signs the same previous transition bundle SHA-256,
**both** old certificate envelope hashes, **both** new certificate envelope
hashes, and exact old and new checkpoint triple (generation, signed-pair
SHA-256, event-head SHA-256) under a separate domain-separated signature.
Only operator IDs differ between the two endorsement bodies. Neither permits
witness-fence retirement.

The complete Stage 263Z keeper event history must contain the old anchor and
terminate **exactly** at the externally supplied new checkpoint, with the
new Stage 264C certificates matching that endpoint. The verifier delegates
full chain audits to the Stage 264C checker for both old and new anchors.

It computes a domain-separated proposed *transition bundle digest* binding
the prior bundle digest, both old and new certificates and both endorsed
envelopes. When the operator separately retains the successor bundle digest,
the --expected-successor-bundle-sha256 flag enforces an exact match. In all
cases this module itself never stores or publishes that digest.

## Running the read-only verifier

    python3 -m tools.audit_record_witness_publication_highwater_lineage \
      /operator-private/checkpoints.db \
      --scope private-wild-arms-publication-mirrors \
      --operator-a-id offhost-highwater-a \
      --operator-b-id offhost-highwater-b \
      --operator-a-public /external/a-public.pem \
      --operator-a-pin ENROLLED_A_PUBLIC_PEM_SHA256 \
      --operator-b-public /external/b-public.pem \
      --operator-b-pin ENROLLED_B_PUBLIC_PEM_SHA256 \
      --old-a-certificate /external/old-a.json \
      --old-a-sha256 INDEPENDENT_OLD_A_CERT_SHA256 \
      --old-b-certificate /external/old-b.json \
      --old-b-sha256 INDEPENDENT_OLD_B_CERT_SHA256 \
      --new-a-certificate /external/new-a.json \
      --new-a-sha256 INDEPENDENT_NEW_A_CERT_SHA256 \
      --new-b-certificate /external/new-b.json \
      --new-b-sha256 INDEPENDENT_NEW_B_CERT_SHA256 \
      --endorsement-a /external/endorsed-a.json \
      --endorsement-a-sha256 INDEPENDENT_A_ENDORSEMENT_SHA256 \
      --endorsement-b /external/endorsed-b.json \
      --endorsement-b-sha256 INDEPENDENT_B_ENDORSEMENT_SHA256 \
      --previous-transition-bundle-sha256 INDEPENDENT_PREVIOUS_BUNDLE_SHA256 \
      --expected-generation TRUSTED_NEW_GENERATION \
      --expected-pair-pin TRUSTED_NEW_PAIR_SHA256 \
      --expected-event-head TRUSTED_NEW_CHAIN_HEAD_SHA256 \
      --expected-successor-bundle-sha256 INDEPENDENT_NEW_BUNDLE_SHA256

Exit code 0 means successful **conditional** verification of submitted
evidence; code 1 reports a fail-closed mismatch. The published JSON report
contains digests and verification flags, never private key material.

## Forks and limits

This mechanism binds one successor to a specific predecessor. It prevents
an *arbitrary different successor* from masquerading as the independently
pinned successor bundle. It does **not** prevent two valid successor bundles
being independently co-signed from the same previous bundle! The two
operators could be compromised or could sign twice. Without an independent
monotonic CAS/trusted transparency log, there is no proof of fork absence,
globally latest state or durable independent retention. A synthetic test
demonstrates two cryptographically valid successors sharing one parent
and differing only in operator seal sequence; an external *committed*
successor hash distinguishes them.

The old/new operator certificates and endorsements do not prove physical
operator independence. The caller must still authenticate the Stage
263V/W PS1 history separately and use Stage 264B/C for fresh dual-source
cross-checks where appropriate. This tool does not contact those sources.

No Nintendo Switch gameplay, emulator run, custody changes, CAS retry,
witness-fence release or deployed independent service is asserted. All
successful reports explicitly retain
externally_persisted_successor_bundle_proved=false,
unique_successor_or_fork_absence_proved=false,
real_external_operator_independence_proved=false,
automatic_cas_retry_authorized=false, and
witness_fence_retirement_authorized=false.
