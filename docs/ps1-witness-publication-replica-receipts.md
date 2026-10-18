# Stage 264H — two separately pinned Ed25519 inspection receipts

Stage 264G compares two *local* copies of a fully signed Stage 264E
equivocation archive. Stage 264H adds a separate signed inspection statement
from each enrolled operator, with a verifier-provided fresh 128-bit nonce,
explicit storage/role identity, exact evidence/archive SHA-256 and
per-operator predecessor receipt hash and sequence.

The reference implementation is
\`tools/audit_record_witness_publication_replica_receipts.py\`.
It does NOT provision any real independent operator, remote archive
service, hardware attestation or immutable retention.

## Signing

The Python function \`attest(...)\` is intended to be called by each
separate operator on **their own** private archive copy. Before signing, it
checks the copy's Stage 264E enrollment scope, exact byte SHA-256 and all
twelve upstream Ed25519 signed envelopes against externally supplied
independent evidence/operator key pins. It confirms the inode and file
bytes did not change between inspection and signing, then signs a canonical
domain-separated Ed25519 receipt, writes it via no-overwrite exclusive
creation and re-reads its signature with the enrolled public key.

Operator receipts each contain these authenticated fields:

- Distinct \`operator_role\` (operator-a / operator-b),
  \`operator_id\` and \`storage_id\`.
- Shared \`checkpoint_scope\` and \`audit_id\`.
- Individually expected 128-bit \`challenge_nonce\`.
- \`receipt_sequence\` and \`previous_receipt_sha256\`.
- Exact full archive SHA-256 and Stage 264E canonical evidence SHA-256.
- \`copy_inspection_performed=true\`, plus explicit false for
  \`external_physical_custody_proved\` and witness-fence retirement.

Only **offline enrolled private keys** should be used by actual operators;
no production private keys are committed to the repository. An attempt to
use the wrong private key can leave a no-clobber receipt artifact that is
later rejected at readback. Never automatically overwrite or retry such
ambiguous outputs.

The reference operator-side command is also exposed as
\`tools/audit_record_witness_publication_replica_receipt_sign.py\`.
It refuses to replace an existing output, and requires a private signing key:

    python3 -m tools.audit_record_witness_publication_replica_receipt_sign \
      /operator-a/private/case.json /operator-a/private/receipt.json \
      --role operator-a --operator-id operator-a --storage-id storage-a \
      --scope private-wild-arms-publication-mirrors \
      --audit-id audit-unique-001 --challenge FRESH_32_HEX \
      --receipt-sequence NEXT_A_SEQUENCE \
      --previous-receipt-sha256 PREVIOUS_A_RECEIPT_SHA256 \
      --archive-sha256 INDEPENDENT_ARCHIVE_SHA256 \
      --evidence-sha256 INDEPENDENT_STAGE_264E_EVIDENCE_SHA256 \
      --evidence-operator-a-public /enrolled/evidence-a.pem \
      --evidence-operator-a-pin EVIDENCE_A_PEM_SHA256 \
      --evidence-operator-b-public /enrolled/evidence-b.pem \
      --evidence-operator-b-pin EVIDENCE_B_PEM_SHA256 \
      --signing-private /operator-a/private/signing-key.pem \
      --signing-public /enrolled/operator-a.pem \
      --signing-public-pin ENROLLED_OPERATOR_A_PEM_SHA256

It emits a proposed receipt envelope SHA-256 for separate operator retention.
It never reports that external retention was carried out.

## Verifying both signed statements and both copies

\`verify(...)\` takes two exact signed receipt envelopes, **independently
retained** SHA-256 pins for each envelope, distinct operator Ed25519 public
keys with externally enrolled PEM pins, both expected role/storage IDs,
distinct challenges and expected previous receipt hashes and sequence
floors. The per-operator new receipt sequence must equal previous + 1.
This makes a prior receipt unusable under a newly and independently
specified challenge/sequence/pin tuple.

The verifier runs the **full Stage 264G double-round comparison** of both
archives before and after verifying the two signed receipts, and rejects a
changed archive identity. Every expected field is compared to the signed
body. Both operator keys must have different DER identities; two names
pointing at the same public key do not form a quorum.

Example verifier CLI:

    python3 -m tools.audit_record_witness_publication_replica_receipts \
      verify /operator-a/private/case.json /operator-b/private/case.json \
      --receipt-a /operator-a/private/receipt-a.json \
      --receipt-b /operator-b/private/receipt-b.json \
      --scope private-wild-arms-publication-mirrors \
      --audit-id audit-unique-001 \
      --operator-a-id operator-a --operator-b-id operator-b \
      --storage-a-id storage-a --storage-b-id storage-b \
      --challenge-a FRESH_OPERATOR_A_32_HEX \
      --challenge-b FRESH_OPERATOR_B_32_HEX \
      --previous-a-sha256 TRUSTED_PREVIOUS_A_RECEIPT_SHA256 \
      --previous-b-sha256 TRUSTED_PREVIOUS_B_RECEIPT_SHA256 \
      --previous-a-sequence OLD_A_SEQUENCE \
      --previous-b-sequence OLD_B_SEQUENCE \
      --receipt-a-public /enrolled/receipt-a-public.pem \
      --receipt-b-public /enrolled/receipt-b-public.pem \
      --receipt-a-public-pin TRUSTED_A_PEM_SHA256 \
      --receipt-b-public-pin TRUSTED_B_PEM_SHA256 \
      --receipt-a-envelope-pin TRUSTED_A_SIGNED_RECEIPT_SHA256 \
      --receipt-b-envelope-pin TRUSTED_B_SIGNED_RECEIPT_SHA256 \
      --primary-pin TRUSTED_PRIMARY_ARCHIVE_SHA256 \
      --secondary-pin TRUSTED_SECONDARY_ARCHIVE_SHA256 \
      --evidence-pin TRUSTED_STAGE_264E_SHA256 \
      --evidence-operator-a-public /enrolled/evidence-a.pem \
      --evidence-operator-b-public /enrolled/evidence-b.pem \
      --evidence-operator-a-pin TRUSTED_EVIDENCE_A_PEM_SHA256 \
      --evidence-operator-b-pin TRUSTED_EVIDENCE_B_PEM_SHA256

CLI exit 0 means both cryptographic statements and local archive
revalidations pass *against the supplied external trust pins*; exit 1
means any invalid/missing/conflicting input. Reports contain digests and
booleans only, never raw envelopes or private signing keys.

## Trust and operational limits

The nonce must be created and retained by an **independent verifier**,
not chosen by an untrusted source. The verifier cannot tell from a
well-formed signed nonce whether it was ever independently generated or
whether an old expected nonce and predecessor receipt pin were replayed
together. Two cryptographic operator keys also do not prove different
people, physical hosts, storage hardware or administrators.

A successful signed receipt means the enrolled key signed a bounded
inspection *claim*; it does not establish independent externally managed
custody, long-term physical durability, fork-free receipt history,
honest operator behavior, globally latest archives or immutable
storage. Both local files can be deleted after verification. If the
last out-of-band pinned receipt hashes are compromised, an older valid
pair may also be replayed.

No actual independent source/keeper hosts are deployed here. No
automatic CAS retry, witness-fence retirement, physical restoration,
Nintendo Switch build or emulator gameplay claim is made.

All success reports keep
\`external_operator_independence_proved=false\`,
\`external_challenge_freshness_proved=false\`,
\`physical_durability_proved=false\`,
\`externally_retained_latest_receipt_pins_proved=false\`,
\`no_concurrent_receipt_fork_proved=false\`,
\`witness_fence_retirement_authorized=false\`,
\`witness_fence_retired=false\` and
\`automatic_cas_retry_authorized=false\`.
