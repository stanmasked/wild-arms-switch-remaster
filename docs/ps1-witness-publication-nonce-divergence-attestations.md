# Stage 264M — two Ed25519 operator statements over detached nonce-fork evidence

Stage 264L saves privately the complete, fully audited history of two
incompatible Stage 264J nonce event chains. Stage 264M adds separate
Ed25519 statements from **two enrolled operator key identities** over the
exact-byte SHA-256 of that archived, checked evidence.

Reference utility:
tools/audit_record_witness_publication_nonce_divergence_attestations.py

The **sign** action replays the full Stage 264L private archive using four
independently supplied historic enrollment pins: primary and secondary
genesis SHA-256, and primary and secondary current event-head SHA-256.
It checks the independently retained archive SHA-256, then signs the
inspected scope, audit ID, conflict classification, common verified event
count, two head/genesis pins, and exact archive SHA-256.

Each operator signs a separately supplied 128-bit challenge, its role and
operator ID, and its own previous signed-attestation SHA-256 and next
attestation sequence. The signed body explicitly fixes all claimed external
custody, automatic-merge and witness-fence-release authorization to FALSE.
The output is a privately created non-overwriting signed JSON envelope.
The operator's public PEM enrollment hash is checked and the signed bytes
are read back and verified before returning their SHA-256.

The **verify** action requires full signed envelopes and independently
supplied envelope SHA-256 pins from both operators, different operator IDs,
different nonces, two distinct enrolled Ed25519 DER key identities, and
external public PEM key pins. It verifies both exact signed bodies against
the actual full Stage 264L archive history, rereading/replaying the private
archive before and after receipt signature inspection. It returns a
redacted JSON report of bound digests and booleans.

Example of a single operator signature:

    python3 -m tools.audit_record_witness_publication_nonce_divergence_attestations \
      sign /private/incident.json \
      --scope private-wild-arms-publication-mirrors \
      --audit-id audit-incident-001 \
      --archive-pin TRUSTED_ARCHIVE_SHA256 \
      --primary-genesis-pin TRUSTED_A_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_GENESIS_SHA256 \
      --primary-head-pin TRUSTED_A_HEAD_SHA256 \
      --secondary-head-pin TRUSTED_B_HEAD_SHA256 \
      --role operator-a --operator-id inspector-a \
      --challenge FRESH_VERIFIER_CHALLENGE_32_HEX \
      --sequence EXPECTED_NEXT_SEQUENCE \
      --previous-attestation-pin PREVIOUS_A_SHA256 \
      --signing-private /operator-private/key-a.pem \
      --signing-public /enrolled/inspector-a.pem \
      --signing-public-pin TRUSTED_INSPECTOR_A_PEM_SHA256 \
      --output /operator-private/inspection-a.json

To verify two signed receipts, replace the sign action with verify, supply
the same scope, audit ID, archive/head/genesis pins, and additionally:

- --operator-a-id and --operator-b-id
- --challenge-a, --challenge-b
- --sequence-a, --sequence-b
- --previous-a-sha256, --previous-b-sha256
- --public-a, --public-b and --public-a-pin, --public-b-pin
- --receipt-a, --receipt-b and --receipt-a-pin, --receipt-b-pin

A successful verification proves ONLY that the enrolled keys signed
two bounded inspection **claims** about one independently pinned,
replayable archive. It does not prove two human operators, physically
separate machines, independent durable retention of either signature
pin, externally generated fresh challenges, a fork-free monotonic
attestation register, honest signers or which fork actually committed.

The operator source archives and nonces are private and must not be
uploaded to the public GitHub repository. No remote operator service,
independent WORM storage or off-host custody was deployed. No automatic
fork merge, ambiguous CAS retry, witness-fence retirement or Nintendo
Switch gameplay progress is authorized or implied.
