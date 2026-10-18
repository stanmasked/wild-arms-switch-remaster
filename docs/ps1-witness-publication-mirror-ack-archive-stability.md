# Stage 264V — archive inode and exact-byte stability during offline replay

Stage 264U introduced a private, create-only, 4 MiB-bounded, exact SHA-256-pinned
archive of two complete and separately enrolled signed mirror-acknowledgment
histories. The archive can be replayed and every Ed25519 completion verified
without the original SQLite databases.

Stage 264V hardens the **existing default Stage 264U inspect path** in:

    tools/audit_record_witness_publication_mirror_ack_detached_evidence.py

An external archive SHA-256 is still required. In addition, before the first
bounded O_NOFOLLOW read the inspector captures the private pathname's device,
inode, size, ownership, permissions, hardlink count, nanosecond mtime and ctime.
After the complete in-memory Stage 264J hash-chain reconstruction and all
completed Stage 264Q Ed25519 verifications, it checks that:

1. The private path still identifies the same owner-private, nonlinked
   regular file with unchanged device/inode, size and relevant timestamps;
2. A **fresh bounded private-file read** returns the exact same byte sequence;
3. The file identity remains unchanged after the second read.

The Stage 264U create path already re-inspects the saved private output
before reporting success, so this strengthens both create-readback and
later standalone inspect invocations.

This checks common malicious or accidental mutations *during* a long
archive audit, including replacing a file with a new inode holding identical
bytes, truncation, appending bytes, replacing with a symlink/directory,
adding a hardlink, weakening filesystem permissions or rewriting the
original bytes during audit. It is still mandatory to verify the caller's
separately retained exact archive SHA-256; the local snapshot is NOT an
independent trust anchor.

The new synthetic regression suite is:

    python3 -m unittest discover -s tests -p test_record_witness_publication_mirror_ack_archive_stability.py -v

Test fixtures swap files at a deterministic point *after* cryptographic
history replay and before returning the inspection result. Tests also
check successful source-free replay after deleting all original SQLite
databases and ensure outputs never claim off-host operator independence,
custody, globally monotonic nonce-CAS, automatic merge or fence retirement.

## Limits

An inode/timestamp double-read cannot establish remote custody, protect
against a privileged attacker who can manipulate the environment outside
the inspected window, or make all operations across a distributed filesystem
atomic. The checks are local and **fail closed for detected mutations**.
The source owner or private key holder can bypass software-only controls.
Neither off-host evidence retention nor trustworthy external pin storage
was deployed. No automatic repair, pending nonce cleanup, witness-fence
release, Nintendo Switch game build or emulator gameplay work is included.
