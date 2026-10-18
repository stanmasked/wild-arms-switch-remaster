# Stage 263K — independently signed observer *claims* for report origin

The Stage 263J composite manifest binds the exact bytes of eight local
research reports. **It does not authenticate how those bytes were generated.**
Stage 263K adds an optional **read-only verifier** of eight separate
Ed25519-signed operator run statements against an independently SHA-256-pinned
catalogue of eight analyzer source files.

The new `tools.audit_record_witness_report_provenance` does not generate
execution proofs, spawn programs, access custody/witness SQLite, or change host
state. The operator's Ed25519 signature authenticates the **claim**, not the
truth of the claimed execution.

## Independently retained code source inventory

An independent operator must capture an exact canonical JSON map:

- schema: `wild-arms-ps1-report-tool-source-index-v1`
- `tools`: exactly eight entries named `preflight`, `quarantine`,
  `cgroup`, `revocation`, `binary`, `interpreted`, `launchers`,
  `activation`
- each entry: the known exact repo-relative source path and the SHA-256 of
  the **raw source file bytes** from the intended code revision

Only fixed tool names/paths are accepted; missing, swapped, duplicate or
additional tools fail closed. The independently enrolled whole-file SHA-256
must be supplied to verification. Creating this source inventory on the
same untrusted host and immediately trusting its own printed hash is **not**
independent provenance.

## Separate signed run claim for each report

An external observer who has independently investigated a specific run
signs eight separate canonical Ed25519 claim envelopes, each with schema
`wild-arms-ps1-report-observer-run-claim-v1`.

Every signed body contains **exactly** these fields:

- `schema`, `observer_tag`, `report_kind`, `report_schema`
- `report_sha256` of the unchanged report bytes
- `source_path`, `source_sha256` and `source_index_sha256`
- `composite_sha256` of the whole Stage 263J composite file
- `original_request_sha256`, `signed_stop_sha256`,
  `stop_session_nonce` copied from the pinned composite session
- `run_nonce`: a separately selected 32-digit lowercase hexadecimal
  run identifier, **different for each of the eight entries**

The signature is over the domain-separated canonical body, using the
same audited Ed25519 format as other witness tooling. Claims must be
created on the independent operator's authorized system after reviewing
the running service, execution logs, report and source. A custody
service must **never** be granted the observer's private signing key.

The verifier requires the explicitly pinned observer public PEM key,
independent SHA-256 pin for the tool-index file and Stage 263J manifest,
all eight **original report files**, all eight **source files**, and all
eight **signed observer claims**.

The claim is rejected if its signature, expected run nonce, tool path,
code hash, report bytes, observer identity, stop-session nonce, original
request digest or composite SHA differs. Duplicate run nonces inside the
eight-entry bundle are denied. The verifier does not maintain a
**cross-session replay registry**.

## Read-only command

```sh
python3 -m tools.audit_record_witness_report_provenance \
  /private/composite-manifest.json PINNED_COMPOSITE_FILE_SHA256 \
  /private/source-index.json PINNED_SOURCE_INDEX_FILE_SHA256 \
  /private/observer-public.pem PINNED_OBSERVER_PUBLIC_SHA256 \
  --observer-tag independent-supervisor \
  --preflight-report /private/preflight-report.json \
  --preflight-tool-source /sources/tools/audit_record_witness_fence_quiescence.py \
  --preflight-signed-run /private/preflight-run-claim.json \
  # Repeat the three --<kind>-... options for the other seven report kinds.
```

The command syntax requires **all 24 per-report file arguments**.
The example line with a comment is explanatory; a real invocation must
include complete `--kind-report`, `--kind-tool-source` and
`--kind-signed-run` flags for all eight kinds.

It emits only a small redacted status report. No report content,
private checkpoint, process argument or signing key is printed.
Both the analyzer files and signed claims must already exist and be
privately accessible under the operator's local file policy.

## What a positive report can and cannot mean

A successful result attests only that a particular **key** signed
statements covering eight report hashes, eight source code byte hashes,
the exact pinned Stage 263J composite and its named session.

**It does not prove** that any tool actually ran, that its binary
matched its source, that report output originated from the claimed
process, that the observer host was uncompromised, or that all eight
measurements refer to one global atomic observation. Even
eight independently signed claims can be false.

The verifier intentionally reports:

- `tool_execution_independently_proved=false`
- `observer_host_integrity_proved=false`
- `cross_run_replay_registry_enforced=false`
- `composite_reports_independently_attested_as_generated=false`
- `continuous_writer_revocation_proved=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`

Any effective durable writer revocation, independent Linux service
inventory or safe negative-result witness-fence release remains
**unimplemented**. Tests use signed **synthetic** claims and do not
establish a live PlayStation/Switch build.
