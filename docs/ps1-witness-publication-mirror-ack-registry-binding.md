# Stage 264T — independently pinned signed mirror-ack registry reconciliation

Stage 264S is a guarded, create-only Ed25519 mirror-audit acknowledgment
signer. It commits each challenge, next sequence, preceding signed
acknowledgment SHA-256, exact Stage 264Q manifest hash and full canonical
Stage 264Q signed-body commitment in a private Stage 264J SQLite reserve
transaction BEFORE calling Ed25519. Successful signing appends a complete
event with the exact signed JSON SHA-256.

Stage 264T adds read-only two-copy reconciliation:

    tools/audit_record_witness_publication_mirror_ack_registry_binding.py

It takes TWO separately SHA-256-pinned private local copies of the
Stage 264S acknowledgment nonce registry in distinct private directories,
along with a private role-ordered list of every **completed** signed
Stage 264Q acknowledgment and its independently supplied exact SHA-256.
The enrolled public Ed25519 PEM keys for both operator roles are required.

## Verification contract

- Stage 264K replays the complete event hash chains in BOTH private
  SQLite copies, twice. Prefix-lagged, forked, missing, unpinned,
  linked or unsafe files fail closed. Neither original file is mutated.
- For every reserve/complete pair, the verifier demands exactly one
  full signed Stage 264Q envelope. The exact-byte SHA-256 must equal
  both the independently supplied envelope pin and the completion row.
- The signature must verify using the *enrolled* operator-role PEM key.
  The complete authenticated body is reconstructed through the original
  Stage 264Q schema, including scope, operator identity, challenge,
  sequence, previous signed digest, both original source-ledger
  genesis/head SHA-256 pairs, signed-completion manifest hash, counts,
  pending roles, and mandatory FALSE external-custody/release flags.
- The signed manifest SHA-256 must equal the original reserve event's
  archive SHA-256. The original Stage 264S whole-body domain-separated
  commitment must equal the reserve event's evidence SHA-256.
- Missing, duplicated, altered, switched-role, additional or
  uncompleted envelope entries never count. Pending reservations remain
  pending. At least one verified completed signature is required.
- A final full Stage 264K reread validates both registry copies again.
  Reports contain only digests, event counts, pending roles and
  negative custody/recovery flags; raw private challenges are redacted.

The private signed-envelope manifest looks like:

    {
      "operator-a": [
        {"path": "/private/ack-a1.json", "sha256": "REAL_64_HEX_SHA256"}
      ],
      "operator-b": []
    }

Use a REAL exact-byte digest independently retained outside the signing
host. The path in the example is illustrative.

Example:

    python3 -m tools.audit_record_witness_publication_mirror_ack_registry_binding \
      /operator-a/private/ack-ledger.db \
      /operator-b/private/ack-ledger.db \
      --primary-head-pin TRUSTED_A_CURRENT_ACK_LEDGER_SHA256 \
      --secondary-head-pin TRUSTED_B_CURRENT_ACK_LEDGER_SHA256 \
      --primary-genesis-pin TRUSTED_A_ACK_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_ACK_GENESIS_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-b-public /enrolled/operator-b.pem \
      --private-signed-manifest /private/all-completed-mirror-acks.json

## Limits

Two local paths are NOT proof of two distinct physical operators, genuine
off-host archival custody, globally consistent cross-host nonce CAS,
externally retained trust pins, operator honesty, or which head is latest.
Stage 264T verifies authenticated signed CLAIMS, and does not re-run
the underlying Stage 264P original source mirror-audit at this stage.
A compromised signing key can sign false claims.

The verifier never merges conflicting histories, automatically recovers
pending challenges, reissues ambiguous signatures or releases independent
witness fences. No native Nintendo Switch gameplay/build is changed.
