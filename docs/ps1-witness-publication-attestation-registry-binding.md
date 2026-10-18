# Stage 264P — bound Ed25519 completion checks for two nonce-ledger views

The Stage 264O operator CLI reserves a nonce in a local SQLite ledger **before**
signing a Stage 264M Ed25519 fork-archive attestation, then appends a
completion with the SHA-256 of the exact signed JSON envelope.

Stage 264K can compare two independently head-pinned local nonce registries,
but equal event chains alone do not establish that the completed signed
outputs actually exist or bind the reserved canonical claims.

The read-only Stage 264P checker adds that evidence binding:

    tools/audit_record_witness_publication_attestation_registry_binding.py

## Inputs and validation

The checker requires:

- **Two locally distinct owner-private SQLite files in different private
  directories**, independently supplied genesis and current ledger-head
  SHA-256 pins, and the enrolled scope.
- Enrolled public Ed25519 PEM files for both roles, whose exact PEM SHA-256
  must match the *registry's* operator enrollment.
- A **private** manifest with exactly two role keys. Each role has an
  ordered list of full signed attestation file paths and their **separately
  retained exact-byte SHA-256 pins**, one for every completed transaction
  in that role's ledger history. Extra or missing files fail closed.

The checker runs the complete Stage 264K twice-audited cross-registry
comparison before and after signature binding. A prefix lag or fork fails
closed and is **never** accepted as a basis for signing. It then walks every
hash-audited reservation/completion pair in event order, checks the exact
signed envelope bytes, verifies the domain-separated Ed25519 signature,
reconstructs the canonical Stage 264M signed body, and compares:

- operator role and enrollment identity, scope and public PEM key;
- exact nonce, receipt sequence, preceding attestation digest;
- exact archived evidence SHA-256;
- domain-separated full-body commitment SHA-256 stored **before signing**;
- exact envelope SHA-256 from the completed ledger row.

Completed events with missing signed envelopes, extra manifests, invented
flags authorizing retirement or archive physical custody, or mismatched
commitments are not accepted. Pending reservations remain pending; they
cannot claim a completed signature. The checker demands at least one
verified completed signature to report successful signed bindings.

Example private signed envelope manifest:

    {
      "operator-a": [
        {"path": "/private/ack-a1.json", "sha256": "SIGNED_A1_SHA256"}
      ],
      "operator-b": []
    }

The indicated SHA-256 values must be actual lowercase 64-digit hexadecimal
digests from a separately trusted record. Strings above are illustrative.

Example:

    python3 -m tools.audit_record_witness_publication_attestation_registry_binding \
      /operator-a/private/attestation-register.db \
      /operator-b/private/attestation-register.db \
      --scope private-wild-arms-publication-mirrors \
      --primary-head-pin TRUSTED_A_CURRENT_LEDGER_SHA256 \
      --secondary-head-pin TRUSTED_B_CURRENT_LEDGER_SHA256 \
      --primary-genesis-pin TRUSTED_A_GENESIS_SHA256 \
      --secondary-genesis-pin TRUSTED_B_GENESIS_SHA256 \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-b-public /enrolled/operator-b.pem \
      --private-signed-manifest /private/signed-envelope-manifest.json

A successful report contains only counts, an observed SHA-256 and bounded
status fields; no nonce, private path, signed envelope or secret key is
printed. Failure is redacted and never authorizes automatic merge, retry
or witness-fence release.

## Critical limits

This proves two **locally observed** independently pinned database files
contain equal hash-chain histories and that completed rows correspond
to authentic signed claims held in the supplied manifest. It does **not**
prove the historical signer truly read the underlying Stage 264L archive,
that any privately supplied digest was retained off-host, that two
physically different operator administrators exist, that remote state
cannot be forked in the future, or that globally monotonic cross-host CAS
exists.

The manifest is sensitive: do not upload real private signed-envelope data
to public repositories. No WORM store, external nonce authority, independent
third-party custody, automatic divergence resolution, witness-fence
retirement or Nintendo Switch game/emulator step is created here.
