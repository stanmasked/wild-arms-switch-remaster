# Stage 263F — bounded /proc inventory of known custody writer processes

Stage 263D observes a previously enrolled Linux cgroup; Stage 263E
checks a previously enrolled masked systemd service and the basic
POSIX permission state of one custody SQLite file. These checks cannot
exclude a **stale binary outside that cgroup**, a different service,
or a writer holding an existing descriptor before a service was masked.

This stage adds a separate, **read-only, fail-closed** Linux `/proc`
scanner in `tools.audit_record_linux_writer_inventory`. It does NOT
identify every possible process capable of *future* SQLite writes,
authorize negative-outcome fence retirement, or change processes.

## Independent binary inventory

An operator separately provisions a private canonical JSON file,
together with the SHA-256 of the **entire file** over a trusted channel.
The catalogue contains all **known** old and current custody writer
executable **paths**. Paths are absolute, sorted, unique and bounded,
and each path has an enrolled SHA-256 for offline version provenance.

Example (synthetic names and example hashes only):

```json
{"executables":[{"path":"/opt/wildarms/bin/custodian-v1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},{"path":"/opt/wildarms/bin/custodian-v2","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}],"schema":"wild-arms-ps1-known-custody-writer-binaries-v1"}
```

The actual file must have **sorted canonical compact JSON followed by
one newline**, and be mode 0600 owned by the scanning operator. The
hashes of the individual files are inventory metadata; the present
scanner matches *live `/proc/PID/exe` symlink paths*, including a
` (deleted)` suffix from removed binaries, rather than claiming to
rehash every live process. The independently pinned file hash prevents
silent modification of the enrolled list, **not omissions** from it.

## Bounded observation

The production CLI requires the observed `/proc` to be a `proc`
filesystem according to its mount information, and scans numeric PID
directories with no-follow descriptors. It reads each process's
`/proc/PID/stat` starttime twice to reject PID identity changes.

For each process it also reads the `exe` symlink and enumerates all
`/proc/PID/fd` entries. It fails closed if any process appears to
execute a known enrolled path or holds an open descriptor to:

- the separately enrolled custody SQLite file, identified by **both**
  device and inode;
- the immediate parent directory of that database;
- an observed SQLite `-wal`, `-shm`, or `-journal` sidecar.

It refuses unreadable/disappearing processes or file descriptors,
symlink PID directory escapes, an exceeded PID/FD bound, invalid
manifest entries, or changed custody filesystem identities. A second
scan detects writers that appear between observations. No PID, binary
path, reservation token or open-descriptor pathname is printed.

```sh
python3 -m tools.audit_record_linux_writer_inventory \
  /witness-private/known-writer-binaries.json \
  INDEPENDENTLY_PINNED_MANIFEST_SHA256 \
  /custodian-private/anchors.sqlite \
  --db-device ENROLLED_CUSTODY_DEVICE \
  --db-inode ENROLLED_CUSTODY_INODE
```

Exit 0 means a **bounded, double local process scan found no matches
to the enrolled binary paths and currently open enrolled SQLite
objects**. Exit 1 indicates a detected writer or an incomplete scan;
exit 2 indicates invalid input or an operating-system failure. The
positive report still asserts
`all_possible_writer_processes_excluded=false`,
`alternate_namespaces_or_database_copies_excluded=false`,
`continuous_writer_revocation_proved=false`,
`witness_fence_retirement_authorized=false` and
`witness_fence_retired=false`.

## Critical limits

- Absence of an open descriptor is **not** proof that a process cannot
  open the database moments later. Some writers open/close SQLite for
  every transaction. A short-lived process may come and go between
  snapshots. Pinned paths cannot discover a **new or renamed writer
  binary not in the inventory**.
- `/proc` only sees tasks in the observer's PID namespace; `hidepid`,
  permission denials and inaccessible descriptors cause safe failure.
  Root/privileged processes may still write despite file mode
  restrictions; alternate mounts or DB copies are unaccounted for.
- A privileged actor could replace the DB or executable, alter
  namespaces or tamper with the manifest's separately trusted
  enrollment. SHA-256 is not a hardware-backed revocation ledger.
- The process starttime guard narrows PID-reuse races but does not
  provide a coherent atomic process snapshot. A successful scan is
  not a global freeze or kernel-enforced process execution ban.
- This tool does not prove that every systemd unit, socket, timer,
  cron entry, service manager or human user capable of writing has
  been enrolled. Combine it with the Stage 263D/E observations;
  none of them *individually or collectively* constitute permission
  to retire an ambiguous witness fence.

Tests synthesize procfs task directories, symlinks and SQLite objects;
no production service or hardware Nintendo Switch game execution has
been validated.
