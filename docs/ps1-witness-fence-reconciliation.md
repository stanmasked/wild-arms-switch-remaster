# Stage 262 — two-admin recovery of an orphaned witness fence

A stage-261 witness fence deliberately never expires. If the custodian loses
its release response or crashes after a committed write, the independent
witness retains the lock. An unchecked administrative reset would create
a time-of-check/time-of-use vulnerability.

Stage 262 implements a **separate offline, explicitly authorized,
applied-only reconciliation**. It never releases a fence just because a
custodian process stopped or a timeout elapsed.

## Trust boundaries and steps

1. Freeze operational access to the affected custody writer (OS and network
   controls, outside this program). Recover the **exact original private
   stage-251 custody request bytes** including request ID, expected custody
   head, reservation secret and any offered checkpoint. This input MUST stay
   secret. Other requests, including legacy unreserved deposits, are not
   eligible for recovery under this protocol.
2. On the custody system, `attest` reads the complete checkpoint ledger,
   reservation state and recovery log in **one SQLite read transaction**.
   It only certifies an **already applied** action:
   - `reserve`: the matching hashed reservation token owns the exact
     expected committed custody head, or has subsequently been committed
     in the immediate next checkpoint;
   - `deposit-reserved`: the exact checkpoint bytes have already been
     committed as the immediate next custody head under the original
     reservation.
   This statement is Ed25519-signed by the custodian, binding the
   domain, custodian identity, exact custody-request digest, fence owner,
   outcome classification and observed custody sequence/receipt.
   **Uncommitted, stale or ambiguous custody state cannot be attested.**
3. Separately provision the exact SHA-256 of the custodian's public PEM
   from a trusted channel on the witness side. Run `prepare` on the
   independent witness to verify the signed custody outcome, confirm
   the exact existing outstanding fence and expected recovery history
   and create a fresh 128-bit nonce-bearing mode-0600 private proposal.
4. Two independent administrators must sign that **same complete
   proposal hash** with their separately pinned Ed25519 keys. They
   should independently review process quiescence and the custody
   result before approving, not merely endorse a certificate.
5. `recover` rechecks the custodian signature and both distinct
   administrator signatures, then inside the witness **BEGIN IMMEDIATE**
   transaction rechecks the complete witness event history and exact
   fence owner/request/head. It records one SHA-256-linked audit event
   **in the same SQL commit** that retires that specific fence.

Once the fence has been retired, the old held token cannot directly
delete or modify a newly acquired fence owned by a different request.
The audit log rejects duplicate reconciliation of the same custody
request. A damaged audit chain blocks normal fence claim/release and
witness recovery-record appends.

## Example private command flow

Capture the original request in a protected file. Run on the *custodian*:

    python3 -m tools.audit_record_witness_fence_reconciliation attest \
      /custodian-private/anchors.sqlite \
      /custodian-private/original-request.json \
      /custodian-private/signing-key.pem \
      /custodian-private/signed-applied-outcome.json \
      --custodian-tag custody01

Deliver the original request and signed result privately to the witness
operator, who must have an independently trusted custodian public PEM:

    python3 -m tools.audit_record_witness_fence_reconciliation prepare \
      /witness-private/recovery-witness.sqlite \
      /witness-private/original-request.json \
      /witness-private/signed-applied-outcome.json \
      /witness-private/pinned-custodian-public.pem \
      PINNED_CUSTODIAN_PUBLIC_PEM_SHA256 \
      /witness-private/fence-reconcile-request.json \
      --custodian-tag custody01

Each administrator independently signs the same proposal using their
protected Ed25519 private signing key:

    python3 -m tools.audit_record_witness_fence_reconciliation approve \
      /admin-alice/fence-reconcile-request.json alice \
      /admin-alice/private-ed25519.pem \
      /admin-alice/approval.json

The second administrator repeats the command with their own identity
and key. The witness then performs final authenticated reconciliation:

    python3 -m tools.audit_record_witness_fence_reconciliation recover \
      /witness-private/recovery-witness.sqlite \
      /witness-private/original-request.json \
      /witness-private/signed-applied-outcome.json \
      /witness-private/fence-reconcile-request.json \
      /witness-private/alice-approval.json \
      /witness-private/bob-approval.json \
      /witness-private/pinned-custodian-public.pem \
      PINNED_CUSTODIAN_PUBLIC_PEM_SHA256 \
      alice /witness-private/alice-public.pem PINNED_ALICE_PUBLIC_PEM_SHA256 \
      bob /witness-private/bob-public.pem PINNED_BOB_PUBLIC_PEM_SHA256 \
      --custodian-tag custody01

Private inputs and output files must be guarded; the CLI prints only
redacted status and audit sequence, never the original request,
reservation secret, public key fingerprint or checkpoint values.

## Safety limitations

**This is not automatic crash resolution.** It only supports proof of
operations observed to have committed. If a request is not committed,
has a disputed outcome, or may still execute in another process,
the lock remains intact. A future procedure needs independently
enforced custody-writer quiescence and a separate decision protocol
for authorizing abandonment without a committed result.

Signed custody attestations are evidence from a *trusted custodian
signing key*, not independently proven real-time statements. If that
key or the witness DB is compromised, the trust basis fails. External
operators must attest to the actual separation of administrator
identities, key enrollment and service accounts. The witness journal is
hash-linked SQLite and NOT an externally immutable transparency log;
two distinct keys do not prove two different human owners.

The original custody service can still be accessed through legacy
paths. There is no cross-database atomic commit, hardware monotonic
counter, auto-expiring lock or independent production deployment.
No original Wild Arms PlayStation execution or playable native
Nintendo Switch remaster is asserted. Synthetic tests use temporary
private keys, test-only custody ledgers and no proprietary game assets.
