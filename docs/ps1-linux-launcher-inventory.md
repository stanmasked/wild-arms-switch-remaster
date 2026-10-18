# Stage 263H — alternative runtime and all-process argv custody audit

Stage 263F inspects known native binaries and custody SQLite descriptors.
Stage 263G adds registered Python interpreters. Neither detects every
invocation of a known custody script or module through a **different**
Python binary, `env`, a shell, Node or other runtime. Stage 263H adds a
conservative, read-only third inventory layer. It **never authorizes
retirement of an uncertain witness fence**.

## Privately enrolled launcher manifest

The independent operator must separately provision and SHA-256-pin
three canonical JSON files: Stage 263F binaries, Stage 263G Python
interpreters and the new Stage 263H alternative launcher manifest.
The third file has schema
`wild-arms-ps1-known-custody-alternative-launchers-v1` and exact
sorted, unique sets of:

- `launchers`: executable paths and SHA-256 metadata for alternate
  runtimes, such as `/usr/bin/bash`, `/usr/bin/node`, `/usr/bin/java`,
  `/usr/bin/env` and old wrapper executables.
- `modules`: known exact Python module names used by custody services.
- `scripts`: absolute paths for custody Python/shell/Node wrapper
  scripts invoked by other executables.

Example (synthetic digest):

```json
{"launchers":[{"path":"/usr/bin/bash","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],"modules":["tools.audit_record_custodian_tls"],"schema":"wild-arms-ps1-known-custody-alternative-launchers-v1","scripts":["/opt/custodian/old-service.sh"]}
```

Store compact canonical JSON, sorted object keys, one final newline, a
private regular file and an independently distributed whole-file hash.
Per-entry binary SHA-256 fields are provenance metadata; the kernel's
`/proc/PID/exe` path is **not cryptographic proof** that executable
memory matches that hash.

## Observation and fail-closed policy

The inspector first runs the Stage 263G composed native/Python
inventory. It then walks all visible numeric PIDs **twice**, using
no-follow process directory descriptors and process starttime checks.
For each PID, it rejects either of these observations:

1. The kernel executable path equals an enrolled alternate launcher
   (also recognizes a trailing ` (deleted)` path suffix).
2. Its bounded, NUL-delimited `/proc/PID/cmdline` arguments contain
   an **exact** enrolled script path or an exact `-m module` pair,
   even when the process uses an **unenrolled interpreter**.

Arguments are matched as separate tokens, not arbitrary text
substrings. An independently enrolled launcher executable is always
refused as a possible writer regardless of its command line.

An unreadable or malformed userspace process command line, PID reuse,
symlink PID-directory escape, incomplete/oversized scan or changing
custody SQLite objects causes a safe failure. Kernel tasks with no
executable and an **empty** procfs cmdline can be ignored; when a
process lacks an executable but has a **nonempty** cmdline, the scan
refuses to treat it as a harmless kernel thread.

Example:

```sh
python3 -m tools.audit_record_linux_launcher_inventory \
  /witness-private/known-writer-binaries.json PINNED_BINARY_SHA256 \
  /witness-private/known-interpreted-entrypoints.json PINNED_PYTHON_SHA256 \
  /witness-private/known-alternative-launchers.json PINNED_LAUNCHER_SHA256 \
  /custodian-private/anchors.sqlite \
  --db-device ENROLLED_DATABASE_DEVICE \
  --db-inode ENROLLED_DATABASE_INODE
```

The command never calls `systemctl`, kills tasks, mutates the custody
database or witness database, unfreezes a cgroup or prints process
arguments. Exit 0 is a **local, bounded negative observation** across
the three enrolled inventories. Exit 1 is a detected potential writer
or incomplete scan; exit 2 means invalid input / OS failure.

The successful report explicitly sets:

- `all_alternative_runtimes_excluded=false`
- `argv_is_authenticated_provenance=false`
- `future_writer_launch_prevented=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`

## Limits that remain

- A new or renamed launcher, an unregistered module/script, a dynamic
  command such as `bash -c '...'` from an **unknown** shell executable,
  another PID namespace, a brief process between snapshots and a
  different custody SQLite copy may evade this observation.
- The kernel process command line can be changed by its owner; it is
  not authenticated evidence of program identity or historical writes.
- This tool does **not** prove that the manifest includes every writer,
  validate independent service-manager restart denial, revoke database
  permissions, or provide a globally atomic kernel process snapshot.
- Combining stages 263A–H still does **not** authorize a negative
  result to be reconciled or a stuck witness fence to be retired.

The included regression tests use synthetic `/proc` directories and
do not attest production service shutdown or Nintendo Switch gameplay.
