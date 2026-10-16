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
