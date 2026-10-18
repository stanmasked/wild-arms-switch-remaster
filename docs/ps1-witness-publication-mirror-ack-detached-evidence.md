# Stage 264U — detached private replay of two complete signed acknowledgment histories

Stage 264T checks two separate private local Stage 264S SQLite
acknowledgment-registries and the exact signed Stage 264Q Ed25519
envelopes for every completed reserve/complete transaction. This stage
adds an **exclusive create-only** PRIVATE evidence archive that remains
auditable after the original two SQLite files have been lost.

Reference tool:

    tools/audit_record_witness_publication_mirror_ack_detached_evidence.py

## Create a privately retained evidence artifact

The create mode takes two individually genesis/head SHA-256-pinned Stage 264S
SQLite acknowledgment-registries in distinct private owner-controlled
directories, two original enrolled Ed25519 public PEM files, and a private
signed envelope manifest with separately pinned SHA-256 values. It runs
the full Stage 264T audit before AND after collecting two complete signed
registry histories. The archive includes the two full enrolled hash-chain
event histories plus both roles' ordered full Ed25519 JSON envelopes,
base64 encoded, each with its exact-byte SHA-256.

Creation is capped at **4 MiB**, uses a private 0600 file in a 0700
directory, O_EXCL / no overwrite and fsync. It independently reconstructs
and reaudits the artifact before creating it, then re-opens it and reruns
the same offline replay against its new SHA-256. An existing/partial
artifact is NEVER erased, overwritten or implicitly retried. The returned
SHA-256 MUST be retained separately by the operator before it can be
considered an independent trust pin.

    python3 -m tools.audit_record_witness_publication_mirror_ack_detached_evidence \
      create /private/mirror-ack-incident.json \
      --primary /private-a/mirror-ack-ledger.db \
      --secondary /private-b/mirror-ack-ledger.db \
      --scope private-wild-arms-publication-mirrors \
      --genesis-a ENROLLED_GENESIS_A_SHA256 \
      --genesis-b ENROLLED_GENESIS_B_SHA256 \
      --head-a ENROLLED_CURRENT_HEAD_A_SHA256 \
      --head-b ENROLLED_CURRENT_HEAD_B_SHA256 \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-b-public /enrolled/operator-b.pem \
      --private-signed-manifest /private/pinned-ack-envelopes.json

The archive contains RAW NONCES, metadata and complete signed operator
envelopes. **NEVER upload the private archive to a public repository or
to public GitHub Actions**, and do not include it in public logs.

## Offline inspect without original databases

For inspection, the original SQLite files are NOT needed. The caller
MUST provide the separately retained archive SHA-256 and the original
two genesis + two head SHA-256 trust anchors and enrolled public PEMs:

    python3 -m tools.audit_record_witness_publication_mirror_ack_detached_evidence \
      inspect /private/mirror-ack-incident.json \
      --archive-pin INDEPENDENT_ARCHIVE_SHA256 \
      --scope private-wild-arms-publication-mirrors \
      --genesis-a ENROLLED_GENESIS_A_SHA256 \
      --genesis-b ENROLLED_GENESIS_B_SHA256 \
      --head-a ENROLLED_CURRENT_HEAD_A_SHA256 \
      --head-b ENROLLED_CURRENT_HEAD_B_SHA256 \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-b-public /enrolled/operator-b.pem

The verifier rejects unsafe links or file permissions, oversized,
noncanonical or duplicate-field JSON, tampered/extra/missing envelopes,
invalid base64, corrupted hash chains, wrong external pin/enrollment and
mismatched registry copies. Both full event histories are rebuilt inside
temporary **memory-only SQLite**, and the original Stage 264J hash-chain
auditor runs on each. Every completed signed Stage 264Q Ed25519 claim is
verified against the *enrolled PEM* and original Stage 264S pre-sign
body commitment and completion hash. Pending reserves remain pending.
The stdout report contains counts, digests and negative safety claims,
not nonce text, raw signed bytes or private archive paths.

## Trust boundaries and limitations

The archive proves a bounded, reproducible **local** record of full
hash-chained histories and cryptographically authenticated signed claims,
conditional on the separately supplied, genuinely trusted external pins.
It does not prove the original Stage 264P source ledgers were inspected
honestly by the operators, physical independence, off-host custody,
real-time challenge freshness, globally monotonic cross-host CAS, WORM,
or which history was the latest. An attacker controlling both sources
and separately provided external hashes can construct an internally
consistent different archive.

This stage never synchronizes conflicting nonce histories, retries
ambiguous signatures, clears pending reservations or authorizes
independent witness-fence retirement. Native Nintendo Switch game
code, emulator testing and gameplay are not changed.
