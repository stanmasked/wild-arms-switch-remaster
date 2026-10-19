# Stage 311 — GitHub Actions queue hygiene

The field gameplay Draft PR has a large number of historical CI jobs from
rapid synthetic gameplay commits. The exact-head Stage 309/310 runs have
remained in GitHub's `queued` state and no successful new guest evidence
can be claimed while they wait for runners.

The six project workflows now declare GitHub Actions workflow-level
`concurrency` using this key:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

A newer run of the **same workflow and event on the same PR/branch** may
cancel obsolete queued/running predecessors, while preserving separate
push and pull-request checks. Different workflows and unrelated branches
use distinct keys. This is scheduling hygiene, *not* a replacement for
successful tests; cancelled old runs are not evidence of correctness.

Stage 311 must still independently verify exact-head Host Core, native
Switch NRO build, host frame captures, disc-analysis and matrix audits,
plus **actual NeXium first-guest screenshot evidence**. No physical
Nintendo Switch run, original assets or save schema changes are implied.
