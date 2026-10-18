# Stage 264S — prevent double signing mirror acknowledgments before Ed25519

Stage 264R detects contradicting signed mirror-audit claims **after**
the operator keys have already signed them. Stage 264S offers a separate,
**opt-in operator-side CLI** that prevents repeated challenges when both
operator roles share one *local enrolled database*.

New tool: tools/audit_record_witness_publication_mirror_ack_nonce_guard.py

It does NOT modify Stage 264Q's verification-only CLI. It does NOT
turn low-level Ed25519 signing into a remotely controlled service.
Anyone holding a private key can bypass this local software policy.

## Enrollment

Create a **third, separate** private Stage 264J nonce ledger specifically
for Stage 264Q mirror acknowledgment signatures: do not share the ledger
with ordinary Stage 264H copy receipts or Stage 264O divergence attestations.

Use Stage 264J's existing initialization CLI to enroll two distinct
operator IDs, two distinct signing public PEM SHA-256 values, distinct
storage enrollment tags and the exact independently retained *previous
mirror acknowledgment* SHA-256 for each. Independently precompute and
preserve the genesis SHA-256 first. Files/directories are owner-private.

A strict next sequence number and previously completed exact signed
acknowledgment are enforced for each role; a 128-bit nonce is unique
across the entire enrolled database.

## Guarded signing CLI

    python3 -m tools.audit_record_witness_publication_mirror_ack_nonce_guard \
      /operator-a/private/source-signing-register.db \
      /operator-b/private/mirror-signing-register.db \
      /operator-private/acknowledgment-nonces.db \
      /operator-private/acknowledgment-a.json \
      --private-signed-manifest /private/pinned-completions.json \
      --scope private-wild-arms-publication-mirrors \
      --audit-id verified-mirror-audit-001 \
      --genesis-a ENROLLED_A_SOURCE_SHA256 \
      --genesis-b ENROLLED_B_SOURCE_SHA256 \
      --head-a EXTERNAL_A_LATEST_SHA256 \
      --head-b EXTERNAL_B_LATEST_SHA256 \
      --role operator-a --operator-id enrolled-operator-a \
      --storage-id enrolled-mirror-ack-store-a \
      --nonce INDEPENDENT_32_HEX_CHALLENGE \
      --sequence NEXT_OPERATOR_A_SEQUENCE \
      --previous-ack-sha256 TRUSTED_PREVIOUS_ACK_A_SHA256 \
      --public-a /enrolled/source-a.pem \
      --public-b /enrolled/source-b.pem \
      --signing-private /operator-a/private/ack-signing-key.pem \
      --signing-public /enrolled/source-a.pem \
      --signing-public-pin ENROLLED_ACK_A_PEM_SHA256 \
      --expected-registry-head EXTERNALLY_RETAINED_ACK_LEDGER_SHA256

The exact source heads and genesis SHA-256 values must come from
separately trusted records, not newly calculated from the files under
review and then silently trusted.

## Signing protocol

1. Run Stage 264P's complete two-registry signed-completion audit and
   check signing role/operator ID and key identity against source enrollment.
2. Build the full canonical Stage 264Q signed body, including every
   signed completion digest, both original source heads, operator identity,
   scope, fresh independent verifier nonce, sequence, predecessor SHA-256,
   plus mandatory **false** release and physical custody claims.
3. Compute a domain-separated SHA-256 of the **whole body**, then insert
   and commit a reserve event in the Stage 264J private acknowledgment
   ledger BEFORE calling Ed25519. Require independently supplied current
   acknowledgment-ledger head SHA-256 in the same transaction.
4. Re-run complete Stage 264P audit, create-only sign, and re-open the
   actual signed bytes to reverify Ed25519 and exact reserved body.
   Re-run the original Stage 264P audit after signing.
5. Commit a corresponding complete event with exact signed-envelope
   SHA-256 and return the next hash-chained acknowledgment-ledger head
   for separate independently managed external retention.

If anything fails after reserve, the entry remains **pending**.
No automatic retry, erase, reconcile, rollback, overwrite or release
command is provided. Signing another nonce by the same role is blocked
while pending. A different role can only use a *fresh* nonce and the
latest externally trusted event head. Already existing output never
gets replaced.

## Important limits

This is **local SQLite transactional exclusion**, NOT distributed
cross-host CAS consensus. Operators on isolated machines could each
sign a duplicated nonce in separate registries. Distinct enrolled PEM
keys do not prove independent physical operators or off-host durable
retention. The independently supplied expected challenge and latest
registry SHA-256 cannot be externally verified by this program.
Private-key holders could directly call lower-level signing routines.

No actual remote operator service, WORM, physical custody, native
Nintendo Switch gameplay, automatic register synchronization or
witness-fence retirement is implemented by Stage 264S.
