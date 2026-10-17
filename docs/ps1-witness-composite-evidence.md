# Stage 263J — composite, independently pinned witness evidence

This step groups the prior eight research reports into a **single
SHA-256-bound capture manifest** while preserving their actual security
limits. It does not run privileged host commands, take new OS
observations, rewrite custody/witness SQLite or authorize retirement
of an indeterminate witness fence.

## Inputs and exact binding

`tools.audit_record_witness_composite_evidence` expects **private,
canonical JSON bytes** from the following stages:

| Capture name | Research report |
| --- | --- |
| `preflight` | Stage 263A exact negative custody/witness snapshot |
| `quarantine` | Stage 263B/C durable custody writer quarantine |
| `cgroup` | Stage 263D signed cgroup v2 observation verification |
| `revocation` | Stage 263E systemd mask + former writer UID access |
| `binary` | Stage 263F native process / SQLite-descriptor inventory |
| `interpreted` | Stage 263G enrolled Python interpreter inventory |
| `launchers` | Stage 263H alternative scripts, modules and launchers |
| `activation` | Stage 263I systemd socket/timer/path activators |

Every report is required **exactly once**. Each must use its exact
versioned schema and precisely enumerated fields, including **true**
for locally completed checks and **false** for all unsatisfied global
revocation or witness-retirement assertions. Any extra field, missing
field, noncanonical encoding, boolean coercion or an unsuccessful
observation fails closed.

The two independent negative custody reports must agree on the
classification: either a reservation was **not observed in the
snapshot** or a checkpoint was **not committed in the snapshot**.
These classifications do **not** prove that no later write occurred.

The composition also requires the exact original private request,
the Ed25519 supervisor stop claim, the independently pinned supervisor
public key, and the matching canonical *raw* cgroup observation.

It verifies the supervisor signature and expected key pin using the
existing Stage 263 code. The signed stop document must match the
original request, witness owner, stop-session nonce and
domain-separated cgroup observation digest. A changed request,
signed stop document, nonce or cgroup bytes invalidates the binding.

The manifest stores only the SHA-256 digests of each entire private
report, each report's versioned schema, and existing observation
digests when supplied. It records the request/fence owner digest,
signed stop hash, stop-session nonce, raw cgroup evidence hash and
the agreed negative classification. It does **not** export original
requests, checkpoint data, process arguments or private keys.

The internal `manifest_sha256` is calculated with domain separation
over the canonical manifest fields *before* that final digest is
added. The complete file is then independently SHA-256-enrolled in a
separate channel.

## Publish, then independently enroll, then verify

The following commands abbreviate private paths. **All eight report
options must be present**, and every file must be private (0600)
according to the existing file access checks.

```sh
python3 -m tools.audit_record_witness_composite_evidence publish \
  /private/original-request.json \
  /private/signed-supervisor-stop.json \
  /private/cgroup-observation.json \
  /private/pinned-supervisor-public.pem \
  PINNED_SUPERVISOR_PEM_SHA256 \
  /private/composite-witness-manifest.json \
  --supervisor-tag independent-supervisor \
  --preflight-report /private/preflight-report.json \
  --quarantine-report /private/quarantine-report.json \
  --cgroup-report /private/cgroup-report.json \
  --revocation-report /private/revocation-report.json \
  --binary-report /private/native-writer-report.json \
  --interpreted-report /private/python-report.json \
  --launchers-report /private/launchers-report.json \
  --activation-report /private/systemd-activation-report.json
```

The output is a **new** private manifest file. Publication reports a
SHA-256 hash of the **complete file**; the operator must retain that
digest **outside the process and custody host** before verification.
It is not an authenticated value merely because the creator printed it.

To check it, rerun the command with `verify` instead of
`publish`, retaining the same input paths and all eight report
arguments, plus:

```sh
  --expected-composite-sha256 INDEPENDENTLY_RETAINED_FULL_FILE_SHA256
```

Verification rejects changed or reordered report bytes, wrong
signatures, a swapped request, mismatched stop-session nonce,
noncanonical bundle bytes, altered internal hashes, changed report
values, or a mismatched independently pinned complete-file SHA-256.

A successful verification report still includes:

- `report_authenticity_independently_proved=false`
- `observations_are_atomic=false`
- `all_writers_durably_revoked=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`
- `native_switch_game_build_verified=false`

## Trust limits and forbidden inference

The reports from stages 263A–I **are not signed and independently
attested as a set**. The composite proves byte integrity against an
external pin and an authentic supervisor statement, but **does not
prove** the report bytes themselves were originally produced by
legitimate operators or came from the same Linux boot, process
namespace, SQLite database, or time window. The reports' local
observation hashes lack sufficient shared raw identifiers to
independently cross-authenticate all measurements.

Publication and verification **do not re-run** cgroup/systemd/process
scans. A process might restart while the manifest is being written;
a different database or alternate service can also remain active.
A captured manifest cannot replace fresh observations, enforced
credential revocation, independent persistent event logging, or a
kernel-backed global execution deny rule.

No unlock or fence-release API is introduced. In particular,
`witness_fence_retirement_authorized=false` even after all eight
reports pass and the SHA-256 pin matches. Synthetic tests protect
only the verifier code and data format, not production quiescence.
