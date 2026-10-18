# Stage 263D — read-only Linux cgroup v2 observation

Stage 263A verifies a separately signed supervisor **statement**.
Stage 263B/C makes updated Python custody writes refuse a quarantine.
Neither step can independently prove that a Linux service exited or will
never restart. This stage adds a **scoped, read-only kernel-state
observation** that can be bound to the supervisor statement, but
**never authorizes retirement of an unresolved witness fence**.

## Trust model

The operator independently enrolls the intended custody service's
cgroup v2 relative path, Linux kernel boot ID, and cgroup device/inode.
These values must come from a channel separate from the service being
inspected. They identify **a particular boot and kernel cgroup object**,
not a permanently revoked service identity.

The CLI accepts only a cgroup v2 mount visible at `/sys/fs/cgroup`
according to the operator's `/proc/self/mountinfo`. It reads the
cgroup tree through no-follow directory descriptors. The production
CLI does not expose arbitrary `/proc` or cgroup filesystem roots.

The observation requires:

- Exact enrolled Linux boot ID, scope, device and inode.
- `cgroup.freeze=1` on the target scope and `frozen=1`,
  `populated=0` in `cgroup.events`.
- Empty `cgroup.procs` **and** `cgroup.threads` for the target
  and all descendant cgroups, with no symlink escapes.
- Two consecutive matching tree observations; fail-closed on
  unexpected subtrees, oversized files, schema errors or changes.
- A bounded canonical observation containing the original private
  custody request's digest, witness-fence owner digest, supervisor
  stop-session nonce, enrolled boot ID and cgroup subtree identities.

The tool uses SHA-256 over a domain-separated canonical observation.
Its digest may be included in the separately Ed25519-signed supervisor
claim's `control_evidence_sha256` field. Verification checks the
trusted public key, claim identity and nonce, the observation digest,
and **recaptures** the same cgroup tree.

## Private two-step command flow

First, after independently enrolling the boot/cgroup identity, capture
the frozen/empty state, **without stopping or freezing any process**:

```sh
python3 -m tools.audit_record_witness_linux_quiescence observe \
  /custodian-private/original-request.json \
  FRESH_SUPERVISOR_STOP_SESSION_NONCE \
  /witness-private/cgroup-observation.json \
  --scope system.slice/custodian.service \
  --pinned-boot-id ENROLLED_KERNEL_BOOT_UUID \
  --pinned-device ENROLLED_CGROUP_DEVICE \
  --pinned-inode ENROLLED_CGROUP_INODE
```

The output is a private file and a redacted report containing the
domain-separated `observation_sha256` digest. A separate supervisor
must sign a stop claim with **exactly that digest** in
`control_evidence_sha256`, and the same
`stop_session_nonce`. Its private key must not be shared with the
observer. Then verify the binding and repeat the kernel observation:

```sh
python3 -m tools.audit_record_witness_linux_quiescence verify \
  /custodian-private/original-request.json \
  /witness-private/signed-supervisor-stop.json \
  /witness-private/cgroup-observation.json \
  /witness-private/pinned-supervisor-public.pem \
  PINNED_SUPERVISOR_PUBLIC_PEM_SHA256 \
  --supervisor-tag independent-supervisor \
  --scope system.slice/custodian.service \
  --pinned-boot-id ENROLLED_KERNEL_BOOT_UUID \
  --pinned-device ENROLLED_CGROUP_DEVICE \
  --pinned-inode ENROLLED_CGROUP_INODE
```

A successful verification means **a signed claim was bound to a
matching, empty frozen cgroup observation at two local read windows**.
It does NOT mean all possible writers are terminated. The report
intentionally sets `external_writer_revocation_proved=false`,
`all_possible_writer_processes_excluded=false`,
`production_quiescence_proved=false` and
`witness_fence_retirement_authorized=false`.

## Why it is not a recovery authorization

- An old process can be outside the enrolled cgroup, in another PID/
  mount namespace, or started **after** the snapshot. Checking a
  frozen and empty cgroup does not disable systemd restart or the
  network listener, and cannot prove all legacy direct-write paths
  are disabled.
- A privileged attacker can move tasks between cgroups, replace
  a cgroup mount/namespace, rewrite custody SQLite or modify the
  host process tree. Device/inode and boot ID pins reduce accidental
  scope confusion, but are not tamper-proof attestations.
- A cgroup freeze does not establish permanent write revocation.
  The tool never freezes, kills, unfreezes or restarts processes
  and never touches custody or witness databases.
- There is no trusted hardware counter, durable externally enforced
  revocation epoch, independently authenticated service inventory or
  cross-database atomic commit.
- The synthetic tests emulate Linux cgroup controls with private
  files; they do not establish a live protected production system.

A **separate** operator-enforced shutdown and permanent denial of
writer credentials and restart paths, auditable from outside the
custody service, are still necessary before considering a protocol
for safely reconciling a negative result. No automatic unlock exists.
Wild Arms PlayStation execution and playable Nintendo Switch builds
are outside this milestone.
