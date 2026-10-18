# Stage 264J — locally atomic pre-sign nonce consumption ledger

The Stage 264H operator-side CLI originally issued signed archive-inspection
receipts without a committed record of previously used 128-bit challenges.
Stage 264I could detect **two already-issued conflicting claims** but could
not stop a repeat before a second signature was made.

Stage 264J adds:
\`tools/audit_record_witness_publication_receipt_nonce_ledger.py\`

The existing operator-side receipt signing CLI,
\`tools/audit_record_witness_publication_replica_receipt_sign.py\`,
now **requires** \`--nonce-registry\` and \`--expected-registry-head\`.
It reserves the challenge in the SQLite ledger and commits it using
\`BEGIN IMMEDIATE\` **before** the Stage 264H Ed25519 signing call.
There is no CLI path to skip this pre-sign reservation.

## Enrollment and trust

A new registry must be explicitly initialized, never silently created when
signing. Its private directory (0700) must be owner-controlled and the SQLite
file is created with O_EXCL, O_NOFOLLOW and mode 0600. Enroll exactly two
distinct operator roles with separately enrolled operator IDs, storage IDs,
SHA-256 pins of their signing public PEMs and initial predecessor
receipt hashes. A domain-separated deterministic **genesis SHA-256** is
derived from the scope and complete enrollment. The operator must obtain and
retain that value **independently** before the registry's initial creation.

The standalone initializer CLI takes:

    python3 -m tools.audit_record_witness_publication_receipt_nonce_ledger \
      init /operator-private/receipt-nonces.db \
      --scope private-wild-arms-publication-mirrors \
      --expected-genesis-pin EXTERNALLY_ENROLLED_GENESIS_SHA256 \
      --operator-a-id private-operator-a \
      --storage-a-id private-store-a \
      --operator-a-public /enrolled/operator-a-public.pem \
      --operator-a-pin ENROLLED_OPERATOR_A_PEM_SHA256 \
      --operator-a-initial-previous-sha256 ENROLLED_A_PRIOR_RECEIPT_SHA256 \
      --operator-b-id private-operator-b \
      --storage-b-id private-store-b \
      --operator-b-public /enrolled/operator-b-public.pem \
      --operator-b-pin ENROLLED_OPERATOR_B_PEM_SHA256 \
      --operator-b-initial-previous-sha256 ENROLLED_B_PRIOR_RECEIPT_SHA256

An offline caller can calculate the expected initial hash with
\`genesis_digest(scope,enrollment)\`, using exactly the full pair of
enrollment records. The initializer validates enrolled PEM pins and
different DER public key identities. It cannot actually perform external
storage of the independently trusted genesis hash.

## Two-step append-only event protocol

The local SQLite tables retain an event journal with hash-chained
**reserve** and **complete** rows. Each reservation binds the operator
role and registered identity, the exact 128-bit nonce, the **next**
receipt sequence, previously completed receipt SHA-256, the signed
archive SHA-256 and the Stage 264E evidence digest.

The registry's full bounded chain is replay-audited inside each SQLite
\`BEGIN IMMEDIATE\` transaction. On reserve:

1. Require caller-supplied expected latest event-head SHA-256.
2. Require exact registered scope, operator identity and public PEM SHA-256.
3. Check there is no previous use of that nonce by **either** operator.
4. Require no pending receipt for the same operator, next sequence and
   exact previously completed signed receipt SHA-256.
5. Append and durably commit a reserve event using FULL synchronous SQLite
   journal before attempting any Ed25519 signing.

On a successful Stage 264H signed receipt, independently reopen and
verify the signed bytes and append a second **complete** event with
the exact receipt SHA-256. The returned updated event-head digest
must be retained outside the untrusted registry to block a coordinated
rollback of the local database and a replayed old nonce.

If signing fails, if the file write is ambiguous, or if completion fails,
the reserve event remains **pending**. There is intentionally NO
rollback, deletion, retry, clear-pending or release command. The operator
must investigate the ambiguous output out of band; subsequent signatures
by the same operator are blocked until the pending reservation is
reconciled under a separately reviewed process (not implemented here).
A different operator can still reserve another unused challenge.

Example of operator signing after enrollment:

    python3 -m tools.audit_record_witness_publication_replica_receipt_sign \
      /operator-a/private/case.json /operator-a/private/receipt.json \
      --role operator-a --operator-id private-operator-a \
      --storage-id private-store-a \
      --scope private-wild-arms-publication-mirrors \
      --audit-id audit-001 --challenge FRESH_INDEPENDENT_32_HEX_NONCE \
      --receipt-sequence 1 \
      --previous-receipt-sha256 ENROLLED_PREVIOUS_A_SHA256 \
      --archive-sha256 TRUSTED_STAGE_264F_ARCHIVE_SHA256 \
      --evidence-sha256 TRUSTED_STAGE_264E_EVIDENCE_SHA256 \
      --evidence-operator-a-public /enrolled/evidence-a.pem \
      --evidence-operator-a-pin EVIDENCE_A_PEM_SHA256 \
      --evidence-operator-b-public /enrolled/evidence-b.pem \
      --evidence-operator-b-pin EVIDENCE_B_PEM_SHA256 \
      --signing-private /operator-a/private/signing-key.pem \
      --signing-public /enrolled/operator-a.pem \
      --signing-public-pin ENROLLED_OPERATOR_A_PEM_SHA256 \
      --nonce-registry /operator-private/receipt-nonces.db \
      --expected-registry-head EXTERNALLY_RETAINED_CURRENT_LEDGER_SHA256

Read-only audit also requires independently retained current head:

    python3 -m tools.audit_record_witness_publication_receipt_nonce_ledger \
      audit /operator-private/receipt-nonces.db \
      --expected-ledger-head EXTERNALLY_RETAINED_CURRENT_LEDGER_SHA256

CLI output is limited to hash values, event counts, pending operator roles,
boolean verification flags and no-release policy. No private signing keys,
raw signed receipts or archive data are emitted.

## Security limits

This provides **local transactional exclusion** in one enrolled SQLite
registry, not an actual external monotonic compare-and-swap service.
If two physical operators each run independent copies of the registry,
those copies do not enforce one global nonce space. The stage does not
claim remote operator service deployment, independent custody, remote
durability, freshness of challenge creation or physical tamper protection.

The signed receipt-generating *Python helper* from Stage 264H remains
callable on its own by developers or maliciously modified software;
the production-style CLI path now uses the guarded wrapper. An attacker
with access to signing private keys can bypass this software policy.
An attacker rolling back the SQLite database *and* the independent head
pin may replay old challenges. A success response does not prove the
new head was actually saved externally.

A pending reservation blocks further signing by that operator; it does
not prove a signing operation took place. The local registry does not
perform automatic recovery, custodian mutation, witness-fence release,
or Nintendo Switch game building. This is synthetic-infrastructure
research only.
