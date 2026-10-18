# Stage 263 (part A) — conservative preflight for indeterminate custody writes

Stage 262 only retires a witness fence when a custodian-signed receipt
proves the exact original operation **was applied**. It must continue to
reject an interrupted or unknown write. This stage adds a read-only,
fail-closed *preflight* for a negative state; it does **not** implement
release, expiration, a new authorization mode or a production shutdown
service.

## What is verified

The operator supplies the canonical **original private** stage-251
custody request (including its secret reservation token), the custodian
and independent witness databases, and a separately signed supervisor
stop claim. The stop claim must contain precisely:

- `schema = wild-arms-ps1-witness-supervisor-stop-claim-v1`;
- the independently configured `supervisor_tag`, exact original request
  SHA-256 commitment and request-derived fence-owner commitment;
- a fresh 128-bit `stop_session_nonce`, a 256-bit process-identity
  commitment and a 256-bit external control-evidence commitment;
- explicit **true** assertions for `process_tree_terminated`,
  `service_restart_blocked`, `network_ingress_blocked` and
  `custody_writer_access_denied`.

The claim must be Ed25519 signed over the domain-separated canonical
body. The verifier checks that signature against a separately provisioned
and pinned supervisor public PEM. It refuses a bad pin, changed claim,
missing assertion, unrelated original request or malformed fields.

With a custody SQLite `BEGIN IMMEDIATE` writer lock held, the preflight
verifies the complete custody checkpoint and recovery histories. Only the
following **snapshot** cases can pass:

1. For `reserve`, the original custody head is unchanged and the
   requested reservation is not present. A previously *committed* different
   reservation is permissible only if it directly formed the current head.
2. For `deposit-reserved`, the original custody head is unchanged and
   the original reservation remains in status `reserved`; the intended
   next checkpoint has not been committed.

While that custody write lock is still held, it opens a second
`BEGIN IMMEDIATE` transaction on the independent witness, verifies the
SHA-256-linked witness history and administrative reconciliation journal,
and demands the *exact* original fence owner, request commitment and
witness head. Both transactions are rolled back without changing any
record, even if the check succeeds.

## Command (private inputs)

The supervisor stop claim is produced by an **independent externally
controlled** process, not by this tool. Its trusted public key and
SHA-256 fingerprint must be delivered through a trusted channel.

```sh
python3 -m tools.audit_record_witness_fence_quiescence \
  /witness-private/recovery-witness.sqlite \
  /custodian-private/anchors.sqlite \
  /custodian-private/original-request.json \
  /witness-private/supervisor-signed-stop.json \
  /witness-private/pinned-supervisor-public.pem \
  PINNED_SUPERVISOR_PUBLIC_PEM_SHA256 \
  --supervisor-tag independent-supervisor
```

Exit code 0 means **the signed claim was authentic and the negative
snapshot was observed**, NOT that it is safe to release the fence.
Exit code 1 means a contradictory state or nonmatching witness fence;
code 2 means malformed or untrusted evidence. No private token, key,
signature fingerprint or checkpoint data appears in stdout.

## Why this is not yet safe abandonment

A supervisor's **signature** proves authorship of assertions, **not**
that the service truly stopped or all legacy write paths are disabled.
`BEGIN IMMEDIATE` makes the negative snapshot consistent with current
SQLite writers but cannot prevent a blocked, idle, resurrected, or
alternative writer from applying the old request after the lock ends.
The two databases have no shared atomic commit. No evidence here proves
an OS process tree exited or that a process cannot restart.

For an actual stage-263 recovery, a *separate implementation* must
install and durably enforce writer revocation / a sealed custody epoch
across **every** write entrypoint (including legacy and recovery paths),
verify OS/network quiescence independently, bind the exact negative
outcome to that epoch, require distinct administrators' approvals and
atomically audit the final witness action. Until then the original
witness fence is intentionally retained.

Tests cover both uncommitted cases, applied operations, wrong owners,
tampered proofs, false stop assertions, conflicting reservations and
non-mutating redacted CLI behavior. They use only synthetic data and
temporary test keys. No production servers or Switch gameplay are
validated.
