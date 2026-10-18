# Stage 264Q — two Ed25519 statements about the complete signed mirrored ledger

Stage 264P already checks two separately SHA-256-pinned, read-only
Stage 264O SQLite nonce registries **and** every completed signed
Stage 264M receipt, including its original pre-sign body commitment.

Stage 264Q adds an independent **verification-only** tool:

    tools/audit_record_witness_publication_signed_mirror_acknowledgments.py

It verifies **two separate Ed25519 operator acknowledgments** that bind one
fully audited Stage 264P result. No unguarded operator-signing CLI is exposed
by this stage; production operator signing must happen through independently
controlled keys and a monitored, separately guarded nonce/sequence service.

## Data that is signed

Every canonical domain-separated signed body includes:

- Enrolled scope, common audit ID, operator role and operator ID.
- Per-operator independent 128-bit verifier challenge, sequence and previous
  signed acknowledgment SHA-256.
- Exact current genesis and head SHA-256 values for BOTH mirrored registries.
- A domain-separated digest of the **role-ordered complete set of exact
  SHA-256-pinned Stage 264M signed completion envelopes**. The digest is
  deterministic regardless of dictionary iteration order, and is sensitive
  to signed-envelope ordering *within* each operator's history.
- The Stage 264P verified signed-completion count, total event count and
  any remaining pending roles.
- Required false flags for independent off-host custody, automatic register
  synchronization and witness-fence retirement.

The verifier requires exactly two full, private, separately SHA-256-pinned
signed acknowledgment envelopes, signed under the Stage 264P enrolled
operator-a and operator-b PEM keys. Those keys are checked against the
original registry enrollment by Stage 264P, not selected by the attacker
solely from the signatures themselves.

Additionally, the verifier reads the independently pinned original operator
**ID** enrollment before and after signature checks. A genuine enrolled
Ed25519 key signing a *different, unregistered operator name* is rejected.

A successful check first runs Stage 264P **in full**, verifies the exact
two signed acknowledgment bodies, then reruns the complete Stage 264P
audit. If any registered Stage 264M envelope is missing/altered or any
mirrored registry changes, the audit fails closed.

Example (private signed completion manifest and signed acknowledgment
files must remain PRIVATE, not uploaded into public GitHub):

    python3 -m tools.audit_record_witness_publication_signed_mirror_acknowledgments \
      /operator-a/private/signing-ledger.db \
      /operator-b/private/signing-ledger.db \
      --scope private-wild-arms-publication-mirrors \
      --audit-id mirror-review-001 \
      --genesis-a ENROLLED_A_GENESIS_SHA256 \
      --genesis-b ENROLLED_B_GENESIS_SHA256 \
      --head-a TRUSTED_A_CURRENT_HEAD_SHA256 \
      --head-b TRUSTED_B_CURRENT_HEAD_SHA256 \
      --private-signed-manifest /private/mirror-signed-completions.json \
      --ack-a /operator-a/private/ack-a.json \
      --ack-a-pin EXTERNALLY_PINNED_SIGNED_A_SHA256 \
      --public-a /enrolled/operator-a.pem \
      --operator-a-id private-operator-a \
      --nonce-a INDEPENDENT_32_HEX_NONCE_A \
      --sequence-a EXPECTED_NEXT_A_ACK_SEQUENCE \
      --previous-a-sha256 EXTERNAL_PREVIOUS_A_ACK_SHA256 \
      --ack-b /operator-b/private/ack-b.json \
      --ack-b-pin EXTERNALLY_PINNED_SIGNED_B_SHA256 \
      --public-b /enrolled/operator-b.pem \
      --operator-b-id private-operator-b \
      --nonce-b INDEPENDENT_32_HEX_NONCE_B \
      --sequence-b EXPECTED_NEXT_B_ACK_SEQUENCE \
      --previous-b-sha256 EXTERNAL_PREVIOUS_B_ACK_SHA256

Every SHA-256 and nonce argument is an illustrative trusted input;
nothing is generated, notarized, independently stored or installed by
the tool. The verifier prints **only** hashes, counts and explicit
negative policy flags, never raw envelopes or challenge plaintext.

## Important limitations

Two cryptographically valid statements mean two enrolled **keys** signed
a bounded summary. They do not prove two physically distinct operators,
genuinely independent external custody, that the signers actually inspected
the archive in real time, that challenges were externally fresh, or that
the separately supplied external signature SHA-256 / predecessor pointers
were saved in a truly monotonic off-host service.

No global nonce registry, automatic divergence merge, automatic signing
retry, remote operator deployment, witness-fence retirement, native
Nintendo Switch game build, or emulator gameplay is authorized.

All successful outputs explicitly retain false for external-custody,
challenge-consensus, operator-independence, automatic synchronization,
CAS retry and witness-fence retirement claims.
