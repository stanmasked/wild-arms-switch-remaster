# Stage 263G — interpreted custody writer inventory

Stage 263F checks enrolled native writer executable paths and open
custody SQLite file descriptors. This misses services executed through
a general-purpose interpreter, for example `python -m
tools.audit_record_custodian_tls` or `python /some/old-service.py`:
the kernel executable path is usually the **Python interpreter**,
not the custody module or script.

The read-only `tools.audit_record_linux_interpreted_writers` adds a
**second, independently SHA-256-pinned** catalogue of installed
interpreter executable *paths* and separately registered module/script
entrypoints. It always reuses the Stage 263F binary/descriptor audit
first and subsequently performs two additional process scans to check
known Python interpreters.

## Strict operator enrollment

Provide two distinct canonical JSON manifests (both protected mode
0600), each with its own independently distributed SHA-256 pin:

1. The Stage 263F `known-custody-writer-binaries-v1` manifest for old
   native executables and live custody DB descriptors.
2. The Stage 263G `known-interpreted-custody-entrypoints-v1` manifest,
   including at least one **exact, absolute Python interpreter
   executable path**, its enrolled SHA-256 provenance metadata, and
   registered modules/scripts.

Sample Stage 263G manifest (synthetic hashes):

```json
{"interpreters":[{"path":"/opt/custodian/venv/bin/python3","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],"modules":["tools.audit_record_custodian_tls"],"schema":"wild-arms-ps1-known-interpreted-custody-entrypoints-v1","scripts":["/opt/custodian/legacy_writer.py"]}
```

Encode the manifest as ASCII-compatible canonical compact JSON with
alphabetically sorted keys and one trailing newline. Lists of
interpreter paths, module names and script paths must be sorted and
unique. Do not derive the **trusted manifest pin** from a manifest
provided by the untrusted target host.

**Conservative design:** Any **living enrolled Python interpreter**
is treated as a possible writer, including `-m`, direct script,
`-c`, stdin (`-`), or unexpected argument patterns. The
module/script list explains what should be enrolled and supports
internal classification, but does NOT whitelist unrelated Python
jobs running in that interpreter. For usable operational results,
dedicate enrolled interpreters to custody jobs. A non-custody Python
process using the same interpreter intentionally blocks the audit.

The inspector checks bounded, NUL-separated `/proc/PID/cmdline`
for enrolled interpreters, verifies PID starttimes, and checks each
process twice. Missing/malformed/unreadable command lines, PID reuse,
or changes to the custody SQLite filesystem objects are fail-closed
conditions. An interpreter appearing only on the second scan also
blocks the audit.

## Read-only CLI

```sh
python3 -m tools.audit_record_linux_interpreted_writers \
  /witness-private/known-writer-binaries.json \
  PINNED_BINARY_MANIFEST_SHA256 \
  /witness-private/known-interpreted-entrypoints.json \
  PINNED_INTERPRETED_MANIFEST_SHA256 \
  /custodian-private/anchors.sqlite \
  --db-device ENROLLED_CUSTODY_DEVICE \
  --db-inode ENROLLED_CUSTODY_INODE
```

The tool never stops or spawns services, edits permissions, reads
checkpoint contents, or releases a witness fence. It returns redacted
JSON, with `witness_fence_retirement_authorized=false` and
`witness_fence_retired=false` even when its two inventories pass.

Exit 0 means that these **enrolled** native and Python executable
paths and **currently observed** SQLite descriptors did not appear
during the bounded scans. Exit 1 means a known writer or incomplete
process scan was observed; exit 2 means invalid inputs or an OS error.

## Incomplete trust coverage

- An alternative Python binary not in the enrolled interpreter list,
  a renamed executable, a different runtime (Perl, Lua, JVM, shell,
  Node), or a newly created wrapper binary can still write.
- Executable per-entry SHA-256 values are catalogue provenance only.
  `/proc/PID/exe` paths do not prove that **process memory**
  matches a particular binary digest. Python command-line arguments
  are mutable by a sufficiently capable process and are not
  authenticated identity evidence.
- An idle or terminated interpreter may reopen the DB after this
  audit, or an interpreter may be started later. Another PID
  namespace or SQLite replica is not fully observed.
- These two manifests cannot prove all historical entrypoints were
  included. A host administrator or alternate service identity may
  bypass modes, process/namespace inspection, and the custody
  write-quarantine code.
- This is not a durable Linux service mask, kernel security policy,
  immutable revocation journal, or evidence of cross-server
  consensus. It does **not** authorize negative-outcome recovery.

Stage 263G uses synthetic procfs test fixtures. No production
custodian/witness service deployment and no Nintendo Switch game
execution are asserted.
