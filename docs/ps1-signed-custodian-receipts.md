# Stage 250 — Ed25519-authenticated private custodian receipts

Stage 249 requires confirmation that a checkpoint has been durably
committed to the separate custodian database before the verifier can
perform another capture operation. Previously its receipt format was
a **self-reported SHA-256 chain**. Anyone who could replace the private
custodian DB and receipt together could forge an apparently consistent
chain. Stage 250 adds an **opt-in Ed25519 signature and a verifier-side
out-of-band public-key pin**, while retaining stage-249's transaction gate.

The implementation is `tools/audit_record_signed_custodian.py`.
It uses OpenSSL's standard Ed25519 provider via a subprocess. There is
no custom cryptographic algorithm, shipped private key, or third-party
Python cryptographic package.

## Independent key ownership (mandatory security boundary)

The **custodian alone** must generate and retain the Ed25519 private
signing key. The verifier receives ONLY the corresponding PEM public key.
The verifier must pin the SHA-256 of the **exact public PEM bytes**
out of band, in a protected trusted configuration *independent of the
incoming receipt and key file*.

Creating a verifier's pin by simply hashing whatever key an untrusted
sender supplies is **not a trust anchor**. The model is secure only if
a malicious recorder/verifier cannot obtain the custodian's private key
or modify the verifier's independently established public-key pin.

The reference script still reads a private custodian SQLite database
locally: no remote service, secure enrollment process, TLS transport,
network channel authentication or independent OS identity is deployed.
The operator must establish those trust boundaries outside this repo.

## Prepare private keys

Run the following commands **only on the custodian**, in a private
mode-0700 directory. Keys are never added to GitHub:

```sh
openssl genpkey -algorithm ED25519 \
  -out /custodian-private/custodian-ed25519-private.pem
chmod 600 /custodian-private/custodian-ed25519-private.pem

openssl pkey \
  -in /custodian-private/custodian-ed25519-private.pem \
  -pubout -out /custodian-private/custodian-ed25519-public.pem
```

Transfer the **public** PEM to the verifier over a separately trusted
channel. Store it in a verifier-owned private directory. Record/pin its
full-file SHA-256 via a separately trustworthy provisioning process.

Choose a stable explicit custodian identity such as
`wild_arms_custodian_01`. This exact tag is included in the signed
message and must match the verifier's configured identity.

## Sign the latest *committed* custody receipt

After stage-248 `deposit` commits a checkpoint, the custodian signs
that latest sequence, exact checkpoint SHA-256 and previous receipt hash.

```sh
python3 -m tools.audit_record_signed_custodian sign \
  /custodian-private/anchors.sqlite \
  /custodian-private/custodian-ed25519-private.pem \
  /custodian-private/signed-receipt-002.json \
  --custodian-tag wild_arms_custodian_01
```

The signature is over a domain-separated, canonical JSON message
containing `schema`, `custodian_tag` and the full stage-248 receipt.
Its 64 Ed25519 signature bytes are represented as lowercase hex.
The signed private envelope is created exclusively (no overwrite).
The private key and raw hashes are never printed to standard output.

If the signing or delivery process crashes after custody has committed,
the custodian can sign the **same last committed state again** at a new
private output path. It does **not** need to deposit another checkpoint.

## Verify using the pinned public key

```sh
python3 -m tools.audit_record_signed_custodian verify \
  /verifier-private/signed-receipt-002.json \
  /verifier-private/custodian-public.pem \
  YOUR_PREVIOUSLY_TRUSTED_PUBLIC_PEM_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

The command checks strict JSON schema, duplicate fields, bounded sizes,
correct custodian identity, exact PEM file hash and Ed25519 signature.
It reports a redacted boolean and never prints keys, receipt hashes,
nonces or private paths.

**An authentic signature can still be old.** This command verifies
cryptographic integrity and signer-key possession, *not current
freshness*. The stage-249 high-water protocol must still compare the
receipt to the custodian's latest state and verifier's pending sequence.

## Signed admission interface

To opt in to signed receipts rather than the unsigned stage-249
interface, use the `bootstrap`, `issue`, `accept` and `ack` commands
of `audit_record_signed_custodian.py`. Each requires:

- The verifier and custodian SQLite databases.
- A private signed receipt envelope.
- The **pinned** custodian public PEM path.
- Its out-of-band trusted full-file SHA-256.
- The expected `--custodian-tag`.

Example signed acknowledgment:

```sh
python3 -m tools.audit_record_signed_custodian ack \
  /verifier-private/sessions.sqlite \
  /custodian-private/anchors.sqlite \
  /verifier-private/signed-receipt-002.json \
  /verifier-private/custodian-public.pem \
  YOUR_PREVIOUSLY_TRUSTED_PUBLIC_PEM_SHA256 \
  --custodian-tag wild_arms_custodian_01
```

After the Ed25519 verification succeeds, the signed interface passes
the exact verified stage-248 receipt to the already-tested stage-249
state machine. Its SQLite `BEGIN IMMEDIATE`, pending checkpoint
digest, one-use nonce protection and idempotent acknowledgment semantics
are unchanged. A forged receipt cannot release pending admission via
the signed interface. A stale but *authentically signed* receipt still
fails when the custodian sequence has advanced.

Exit codes: **0** successful verification or operation, **1** ineligible
capture or refused pending/rollback state, **2** invalid signature,
wrong key/identity, malformed receipt or unsafe private input.

## Privacy, testing and unresolved threats

Synthetic CI fixtures generate temporary Ed25519 keypairs and synthetic
checkpoint data using the runner's `openssl`; no keys are committed to
the repo. The signed envelope contains only salted-by-context
domain-separated SHA-256 commitments and chain counters, not original
PlayStation memory or game binaries.

This project still does **not** provide TLS/client authentication,
custodian deployment, independent key provisioning, secure key rotation,
key revocation, a hardware-backed key, a trusted append-only third-party
checkpoint, or cross-database atomicity. An independent custodian could
sign incorrect checkpoints; Ed25519 verifies **who signed the message**
only when the key is securely owned and pinned, not whether the original
debugger capture was truthful. Coordinated verifier/custodian rollback
can replay an authentically signed old state absent an external
monotonic high-water authority.

Stage-245, stage-247 and stage-249 admission commands remain available
and **bypass mandatory signature verification**. Operators must enforce
the new interface exclusively to rely on signature authentication.

Original Wild Arms PS1 execution, the game's record structure size
and a native Nintendo Switch game build remain **unverified**.
