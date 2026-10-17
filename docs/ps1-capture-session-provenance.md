# Stage 243 — claimed PS1 debugger session provenance (private)

Stage 242 verifies the raw bytes of two JSONL streams against the user-owned
EXE and temporal claim. This stage adds a **separate, opt-in layer**:
`tools/audit_record_capture_provenance.py`. The old stage-242 format, tool
and tests remain unchanged.

**Security boundary:** a debugger's name/version, binary SHA-256, capture
mode, session nonce and collector receipts supplied by a user are *claims*.
This tool detects missing/inconsistent claims and swapped or tampered files;
it **cannot** independently authenticate the executable debugger binary,
collector identity, runtime settings, timestamps, or actual PlayStation
hardware execution. Matching hashes and receipts alone are not signatures.
Anyone controlling both the logs and their receipts can fabricate a fully
self-consistent bundle.

## Private bundle layout

The stage-242 inputs are kept in their original format: exact extracted
PS-X EXE bytes from a private disc, inventory, temporal claim JSON,
binding manifest JSON, and two JSONL memory streams.

Stage 243 requires **three additional private UTF-8 JSON objects**:

1. A session provenance claim (max **8192 bytes**).
2. A before-collector receipt (max **4096 bytes**).
3. An after-collector receipt (max **4096 bytes**).

Every JSON object must have precisely its documented fields. Duplicate keys,
unknown fields, invalid scalar types, oversized inputs and wrong raw-file
digests are rejected. The session nonce is a nonzero 128-bit value represented
as exactly 32 lowercase hexadecimal characters; use a freshly generated
unpredictable value for each capture rather than the illustrative value below.
The tool cannot guarantee that it was freshly generated.

### Session provenance object

```json
{
  "schema": "wild-arms-ps1-session-provenance-v1",
  "session_nonce": "0123456789abcdeffedcba9876543210",
  "stream_binding_manifest_sha256": "<sha256 of exact stage-242 manifest bytes>",
  "debugger": {
    "name": "synthetic_debugger",
    "version": "0.1.0-test",
    "binary_sha256": "<claimed sha256 of debugger program>",
    "platform": "linux-x86_64"
  },
  "capture_conditions": {
    "target_kind": "emulator",
    "cpu_backend": "interpreter",
    "event_clock": "debugger-counter",
    "sample_mode": "halted-breakpoint"
  }
}
```

The two SHA fields shown with placeholders must be **64 lowercase hex
characters**, with no extra `0x` prefix. The debugger SHA is a declaration,
not a file read: this tool has no access to an independently sourced debugger
binary or trusted build/release attestation.

Allowed capture conditions are exactly:

| Field | Allowed values |
| --- | --- |
| `target_kind` | `emulator`, `hardware`, `unknown` |
| `cpu_backend` | `interpreter`, `dynarec`, `unknown` |
| `event_clock` | `instruction-order`, `debugger-counter`, `unknown` |
| `sample_mode` | `halted-breakpoint`, `step-then-sample`, `unknown` |

These are recorded operator declarations; the values, including
`hardware`, are never treated as proof of the environment.

### Two separate collector receipts

Each receipt is a separate JSON file bound to the exact bytes of the stage-243
session provenance and its corresponding original stage-242 JSONL stream.

```json
{
  "schema": "wild-arms-ps1-collector-receipt-v1",
  "role": "before",
  "session_nonce": "0123456789abcdeffedcba9876543210",
  "collector_tag": "memory_watch",
  "provenance_sha256": "<sha256 of exact provenance JSON bytes>",
  "stream_sha256": "<sha256 of exact before JSONL bytes>",
  "observed_rows": 6,
  "first_event_sequence": 10,
  "last_event_sequence": 60
}
```

Replace the example counters with the *actual first and last JSONL event
counters*, and use the original stage-242 manifest's `collector_tag`.
The other receipt uses `role: "after"` and its own collector tag, byte digest
and counter range. Both receipts must contain the exact same session nonce as
the provenance claim and its digest. The old stage-242 tool still verifies
each JSONL row against the EXE and claimed temporal windows, and stage 243
recounts rows and first/last counters from the raw streams rather than
trusting the numbers in the receipts.

### Read-only local use

```sh
python3 -m tools.audit_record_capture_provenance \
  /private/WildArms.bin \
  /private/disc-inventory.json \
  /private/temporal-slot-snapshots.json \
  /private/capture-manifest.json \
  /private/before-watch.jsonl \
  /private/after-snapshot.jsonl \
  /private/session-provenance.json \
  /private/before-receipt.json \
  /private/after-receipt.json
```

Exit **0**: provided stage-242 data and all stage-243 metadata are
self-consistent. Exit **1**: all inputs parse and are linked correctly but
a prior stage-242 claimed snapshot conflicts with the EXE/temporal claim.
Exit **2**: malformed, oversized, incomplete, corrupt or digest-mismatched
private evidence (`invalid_private_input`, without a detailed public
failure reason).

The report reveals only aggregate counts and conservative booleans. It does
**not** export source addresses, sampled memory words, EXE/debugger digests,
session nonces, debugger names/versions, local filenames, raw stream rows or
runtime settings. Do not upload original discs or private capture data to CI.
GitHub Actions uses synthetic fixtures only.

## Boundaries for future research

These receipts are not signatures or independent trust anchors. Reliable
origin verification would need an *independently authenticated* collector
binary or debugger build, a trusted capture-device identity, and an
attestation/log-signing mechanism with key lifecycle and anti-replay policy.
Even that would need careful evidence to distinguish emulated PS1 behaviour
from execution on original hardware. No such certification is claimed here.

The statically observed multiply factor `2708` does **not** establish the
actual Wild Arms structure size. No native Nintendo Switch game build has
been authenticated. These provenance checks do not change those findings.
