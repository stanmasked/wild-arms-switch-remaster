# Stage 226 — GitHub Actions runner-bootstrap incident triage

The stage 225 draft PR [#1](https://github.com/stanmasked/wild-arms-switch-remaster/pull/1)
has failed GitHub Actions checks. **Do not label these as code-test failures
without recorded executed steps or test output.** This document records
observable REST metadata only; it does not establish the infrastructure root cause.

## Observed on 2026-10-16 (UTC)

- PR run `38976711561` (matrix audits) had two failed jobs,
  `python-audits` and `host-ctest`, each with `runner_name: ""` and
  `steps: []`, completing approximately two seconds after start.
- PR runs `38976711604` (disc tests) and `38976711647` (host core tests)
  showed the same empty-runner/empty-steps failure shape.
- The **main branch** also showed that shape before PR #1 existed:
  run `38976098458` for matrix audits and runs `38976217293` /
  `38976217477` for host/disc checks, so the red checks are not
  isolated to this PR's code.
- Downloading the failed job logs returned 404/BlobNotFound, and the
  normalized job-steps endpoint returned no steps.

These observations support **failure before user build/test steps**. They
do not prove a GitHub service outage, a runner quota, billing failure,
repository policy, or a Python/C++ regression. Do not claim a passed suite.

## Safe repeatable audit

Use an authenticated local GitHub CLI session with access to this private
repository. Never paste access tokens, job logs, private game captures or
raw API responses into issues or CI output.

```sh
gh api repos/stanmasked/wild-arms-switch-remaster/actions/runs/38976711561/jobs |
  python3 -m tools.audit_actions_job_bootstrap --jobs-json -
```

The analyzer accepts the REST `/actions/runs/{run_id}/jobs` JSON object,
checks the input size, and prints only numeric counts and booleans.
`all_returned_failures_pre_runner=true` means **only** that every returned
failed job has an empty runner name and an explicitly empty steps array.
`partial_job_page=true` warns that the API reported more jobs than were
returned; retrieve the other pages before drawing conclusions.
Missing metadata is `failed_without_sufficient_evidence`, not inferred
to be a bootstrap failure. `infrastructure_root_cause_proven` and
`test_failure_proven` intentionally remain false.

Run the standalone synthetic contract tests locally:

```sh
python3 -m unittest discover -s tests -p test_audit_actions_job_bootstrap.py -v
python3 -m unittest discover -s tests -p test_mips_matrix_arithmetic_attribution.py -v
python3 -m unittest discover -s tests -p test_ps1_arithmetic_matrix_attribution.py -v
```

The complete host build still requires a working CI runner or a local host
environment capable of `cmake --build` and `ctest`. A successful run of
only the bootstrap classifier is **not** verification of the PS1 matrix
analyzer or a native Switch build.

## Next operational checks

Review the affected repository's GitHub Actions run summary for explicit
workflow-start errors, Actions permissions and runner availability, and the
account's available Actions minutes/spending limits. Those are **possible
investigation paths**, not diagnosed causes. Once workflow steps appear,
inspect the first failing step and its log, repair a reproducible code
regression if found, and keep PR #1 draft until all required suites pass.
Never merge while the cause or test result is still unknown.


## Stage 227 — corroborated failure boundary and Actions annotations

GitHub's run history contains **both** executions with a provisioned runner
and zero-step failures. This rules out treating every red check as the
same type of problem. Selected independently fetched REST examples
(UTC, 2026-10-16):

| Run ID | Created (UTC) | Observed runner/steps |
|---|---|---|
| `38863373868` | 06:49 | named GitHub-hosted runner, 7 steps, success |
| `38865926450` | 07:14 | named runners, 8–9 steps, failures |
| `38941028160` | 17:36 | named runner, 8 steps, failure |
| `38942396412` | 17:47 | named runner, 7 steps, failure |
| `38943926131` | 17:59 | empty runner, zero steps, failure |
| `38945078291` | 18:08 | empty runner, zero steps, failure |
| `38977680585` | 22:45 | both jobs empty runner/steps, failure |

The available samples locate a **transition interval** between 17:47
and 17:59 UTC, not necessarily the precise first affected job. Some
earlier red jobs actually ran code and must be investigated separately
using their own job logs when accessible. Jobs with `steps: []`
provide **no evidence that Python or C++ tests ran**.

The commit check-run REST metadata for PR #1 also shows
`output.annotations_count: 2` for affected failed checks, even when
`output.summary` and `output.text` are empty. The connected API does
not expose annotation contents; do **not** invent an error message.
Open the actual failed check in GitHub's web interface and read those
annotations. In particular, look for GitHub's explicit Actions budget,
spending/payment, account verification, disabled runner or policy errors.
These are hypotheses, not an established diagnosis.

Official troubleshooting reference:
https://docs.github.com/en/actions/how-tos/troubleshoot-workflows

Since this is a private repository with GitHub-hosted runners, check the
**repository owner's** Settings → Billing and licensing / Billing and
plans → Actions usage, spending limits, budgets, outstanding payments,
and verification prompts, plus repository Settings → Actions → General.
The wording of menus may vary. Raising a budget or adding a payment
method is a financial decision and must **not** be automated without
the owner's choice.

If run annotations reveal an account-wide runner provisioning/billing
block, resolve it on GitHub rather than weakening test assertions,
changing code semantics or switching off CI. If the billing/permissions
screen is healthy yet the issue persists, pass the affected run/job IDs
to GitHub Support. Re-run a small affected workflow **once** only after
addressing a suspected cause; repeated identical failures do not prove
code regressions.

Verification gate: PR #1 stays draft and unmerged. Its newly written
stage 225 lineage tests and the full host suite remain **not verified**
by GitHub Actions while there are no executed steps. The nine local
stage 226 bootstrap-classifier tests independently pass under Python
3.13, but they are only tests of that diagnostic tool.


## Stage 228 — real executed test failures recovered from historical job logs

Unlike the later zero-step runner failures, several older GitHub-hosted
jobs **did execute**. Their logs were recovered through the authenticated
GitHub job-log endpoint and must be treated as *actual code failures*:

- `116858676010` (disc Python test job): 59 tests, **four errors** in
  `test_gp0_matrix_context_cfg` / `test_gp0_matrix_context_sources`.
  They all originate at
  `tools/audit_gp0_matrix_context_cfg.py` when native Python
  `sorted(edges)` tries comparing a normal CFG node `(pc, None)`
  with its delay-slot version `(pc, controller_pc)`:
  `TypeError: '<' not supported between instances of 'NoneType' and 'int'`.
- `116858676561` (matrix host CTest) and `116858676255` (host core)
  corroborate the same graph error. Two affected CTest test modules
  failed, though many unrelated host tests completed successfully.
- `116858676050` (a different disc Python job) shows an **additional**
  record-stride failure: `test_verify_record_stride` expected
  `364`, but the exact `INDEX_WORDS` sequence and final shift
  currently compute `2708`. That test run reported 403 tests total,
  with one assertion failure and the same four graph errors.

### Implemented in the stage-225 draft branch, not main

1. CFG edges are now ordered with an explicit `(PC, controller or -1)`
   sort key; normal and delay-slot nodes remain distinct. A new
   regression checks deterministic ordering and four actual edges from
   a BEQ-to-own-slot fixture (both conditional outcomes included).
2. The `BLTZL` context-source regression previously encoded
   `BLTZL $zero`, which is **always not taken**. It now uses an
   unknown `$t0` source so the branch-likely path genuinely
   exercises both taken and annulled alternatives. The existing
   zero-register predicate tests remain in place.
3. The record-stride inspection used to hard-code `stride_bytes=364`
   even though the checked-in eight MIPS index words compute `677`
   units, multiplied by four by the subsequent `SLL`, i.e.
   `2708`. It now **fails closed** with a generic `ValueError`
   rather than emitting an unsupported 364-byte attestation.
   Synthetic tests record the arithmetic discrepancy and require
   refusal of the contradictory prefix. The correct **original-game**
   record stride remains **unresolved**; no guessed replacement
   for 364 is claimed. Authentic original debugger/EXE evidence is
   needed before changing record layout or reporting verified stride.

The fixes target specific source/test failures confirmed by historical
logs. They **do not prove** the current PR tests pass: fresh GitHub
Actions still fails to allocate a runner, and the complete PS1
regression suite has not been rerun successfully. Avoid merging until
a runner or independent full local regression is available.


## Stage 229 — recovered caller CFG provenance test crash

The last inspected **executed** host job before the later no-runner
failures, run `38942396412` / job `117113025777`
(2026-10-16 17:47 UTC), contains an additional reproducible
Python error, distinct from both the context-edge sort issue and
the REGIMM fixture issue:

```text
ValueError: too many values to unpack (expected 2)
```

In `tools/mips_caller_cfg_sources.py`, each successfully explored path
is appended as a *triple* `(register_origins, pending_load, pc_path)`.
The `load_pending_on_any_path` check incorrectly unpacked that triple
as `(register_origins, pending_load)`. The bug caused errors in the
caller-CFG source tests and downstream probe-path/preflight and
runtime-correlation suites; it does **not** demonstrate that any
arithmetic or control-flow value from the original PlayStation
was wrong.

The draft-branch implementation now correctly unpacks three fields
and keeps pending-load checks scoped to the register of interest.
Two new synthetic regressions cover a pending LW in the delay slot
of JAL after two possible conditional paths, and the absence of
a pending load on a straight-line call. Existing replay/preflight
and caller-CFG suites exercise the same defect from different layers.

As of this entry, this fix has been code-reviewed against the exact
source and historical traceback but **not independently verified by
a complete successful GitHub Actions or CTest run**. Later CI
attempts still report empty runner names and zero steps. That
infrastructure failure must not be misrepresented as a fresh
test assertion against the patch. PR #1 stays draft and unmerged.
