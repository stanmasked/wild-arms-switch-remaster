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
