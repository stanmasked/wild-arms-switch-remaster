# Stage 263E — observational systemd restart and custody UID access audit

This is an **advisory, read-only** extension of
[Stage 263D](ps1-linux-cgroup-quiescence-observation.md). It does not
mask, stop, kill, restart, chmod, change owner, or write to a custody
database. It cannot retire a witness fence.

The operational objective is to reduce a specific ambiguity: an empty
frozen custody cgroup does not tell us whether systemd is configured to
restart the service, or whether the former service account still has
ordinary permissions to write the custody SQLite file.

## Requirements checked

An independent operator enrolls these values outside the custody
service: the exact systemd **system** unit name, the **numeric UID**
formerly used to run that service, the full custody SQLite path and its
expected device/inode, the cgroup v2 relative scope plus its
device/inode, and the current kernel boot ID.

`tools.audit_record_linux_writer_revocation` checks, without changing
the host:

1. The exact systemd unit, via a bounded `/usr/bin/systemctl --system
   show` read. Fail closed unless `LoadState=masked`,
   `UnitFileState=masked` (not `masked-runtime`),
   `ActiveState=inactive`, `SubState=dead`, `CanStart=no`,
   `NeedDaemonReload=no`, `MainPID=0`, `ControlPID=0`,
   `Job=0` and `FragmentPath=/dev/null`. Duplicate, unknown,
   missing or contradictory fields are rejected.
2. The enrolled custody DB is an exact private regular file, accessed
   through `O_NOFOLLOW` descriptors. Its device/inode must match the
   independent enrollment. It and its immediate parent directory
   must both be owned by a UID **different from the enrolled service
   UID**, with no group/other mode bits. Numeric service UID 0 is
   prohibited.
3. The previously saved, canonical cgroup observation is still
   bound to the independently pinned Ed25519 supervisor stop claim
   and the exact custody request. The cgroup tree is inspected again.
4. The systemd properties and custody filesystem identity are read
   **again**. Any difference between the two observations refuses
   a positive advisory report.

The report includes a domain-separated hash of the combined
observation, while explicitly recording:

- `durable_global_writer_revocation_proved=false`
- `alternate_processes_or_privileged_writers_excluded=false`
- `production_quiescence_proved=false`
- `witness_fence_retirement_authorized=false`
- `witness_fence_retired=false`

## Invocation

Use independently collected service/custody identity pins and the
signed supervisor stop claim from Stage 263D. No service-control
changes are made by this command.

```sh
python3 -m tools.audit_record_linux_writer_revocation \
  /custodian-private/original-request.json \
  /witness-private/signed-supervisor-stop.json \
  /witness-private/cgroup-observation.json \
  /witness-private/pinned-supervisor-public.pem \
  PINNED_SUPERVISOR_PUBLIC_PEM_SHA256 \
  /custodian-private/anchors.sqlite \
  --supervisor-tag independent-supervisor \
  --cgroup-scope system.slice/custodian.service \
  --pinned-boot-id ENROLLED_BOOT_UUID \
  --cgroup-device ENROLLED_CGROUP_DEVICE \
  --cgroup-inode ENROLLED_CGROUP_INODE \
  --service-unit custodian.service \
  --service-uid ENROLLED_SERVICE_UID \
  --db-device ENROLLED_DATABASE_DEVICE \
  --db-inode ENROLLED_DATABASE_INODE
```

The result is either a redacted positive advisory report, a rejected
observation, or an invalid-input report. The CLI does not export any
custody reservation token, private checkpoint or signing key.

## Limits: this is not a durable access revocation

- This tool **does not perform** `systemctl mask --now`; an independent
  trusted operator must implement and verify host policy. The masks
  observed here can be removed later by sufficiently privileged actors,
  and another differently named unit, timer, socket, container or
  executable can still issue custody writes.
- A denied numeric UID is only a **basic POSIX mode** check at the
  enrolled file/path. Supplementary privileges, root, capabilities,
  extra mounts, other SQLite copies, inherited open descriptors,
  hard links, ancestor path redirection and direct privileged SQL
  changes are not globally excluded.
- A stopped service is not proof of a quiesced entire host. systemd,
  Linux cgroup, mountinfo, process and file observations are trusted
  only as snapshots within the observer's namespace. A compromise of
  the observer, PID 1, root or kernel invalidates this premise.
- The combined observation hash is not an independent signature or
  immutable log. A nonce in the signed stop claim is **not**
  replay-registered by this tool. The underlying custody/witness
  SQLite stores are not cross-database atomic.
- This stage has no permanent denial of writer credentials, no
  verified complete inventory of all writer entrypoints, and **no**
  administrative authorization to retire an ambiguous witness fence.

Synthetic tests use private files and mocked systemd output; they do
not assert successful quiescence of a production Linux machine or
successful PlayStation/Nintendo Switch game execution. PR remains
Draft until independently run CI and further audit.
