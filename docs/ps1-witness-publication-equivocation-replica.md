# Stage 264G — two-copy private evidence comparison (local reference)

Stage 264F can save and later revalidate one complete Stage 264E double-signed
equivocation archive. Stage 264G checks **two exact copies of the same signed
evidence archive**. It requires independently supplied archive hashes and
cryptographically revalidates both underlying archives, rather than assuming
two equal filenames, two equal hashes supplied by one host, or two filesystem
paths mean real independent custody.

New reference utility:
tools/audit_record_witness_publication_equivocation_replica.py

## Replicate once, never overwrite

The replicate action requires one existing signed archive, its
**independently authenticated** exact-byte SHA-256, separately authenticated
canonical Stage 264E evidence SHA-256, two pinned Ed25519 operator public keys,
and an empty destination filename in a *different private directory*.
Both immediate parent directories must be regular owner-controlled private
directories (mode 0700); the source must be a regular privately owned file
(mode 0600). Neither symlinks nor hardlinks are accepted for archive copies.

It reopens, hashes and fully signature-verifies the source, then confirms the
source inode and file content did not change. It exclusively creates the new
archive with O_EXCL/O_NOFOLLOW and fsyncs file and parent directory. It does
not overwrite existing files. Both copies are then rechecked by the same
strict two-copy audit used by the verify command.

The returned archive SHA-256 still needs to be independently retained by
the destination administrator. The tool cannot do that external action.
If creation is followed by an interrupted acknowledgment or failed readback,
**do not automatically retry**; the target file may already exist and must
be inspected.

## Verify both copies

Verify requires **separately provided** primary and secondary archive
SHA-256 pins, an independently authenticated Stage 264E evidence SHA-256,
two trusted public PEM SHA-256 pins, and both private file paths.
It rejects pins that differ: the copies are required to have byte-for-byte
identical signed evidence, even though independent operators may maintain
separate off-host copies in practice.

For each of two audit rounds it:

- Confirms source and replica have different parent directory inode IDs,
  distinct regular file inode IDs, mode/owner restrictions, no symlinks and
  no hardlinks.
- Reads both full bounded archives and checks exact-byte hash against their
  separately provided SHA-256 pins.
- Confirms byte-for-byte equality, not merely the two reported digest values.
- Calls the Stage 264F cryptographic verifier separately on both copies,
  including all twelve Ed25519 signed evidence envelopes, both operator
  signing keys, and canonical evidence hash.
- Rereads both files and reconfirms file and parent identities. A changed
  file or identity during/between observation rounds fails closed.

The returned report only claims that two **local** copies were observed as
different private files with cryptographically consistent bytes. No copy is
accepted as independently administered just because it is in another
directory.

Example (the directory layouts shown are only illustrative):

    python3 -m tools.audit_record_witness_publication_equivocation_replica \
      replicate /operator-a/private/case-001.json \
      /operator-b/private/case-001.json \
      --primary-pin TRUSTED_ARCHIVE_SHA256 \
      --evidence-pin TRUSTED_STAGE_264E_EVIDENCE_SHA256 \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-a-pin TRUSTED_OPERATOR_A_PEM_SHA256 \
      --operator-b-public /enrolled/operator-b.pem \
      --operator-b-pin TRUSTED_OPERATOR_B_PEM_SHA256

Subsequent audit:

    python3 -m tools.audit_record_witness_publication_equivocation_replica \
      verify /operator-a/private/case-001.json \
      /operator-b/private/case-001.json \
      --primary-pin OPERATOR_A_INDEPENDENTLY_SAVED_ARCHIVE_SHA256 \
      --secondary-pin OPERATOR_B_INDEPENDENTLY_SAVED_ARCHIVE_SHA256 \
      --evidence-pin TRUSTED_STAGE_264E_EVIDENCE_SHA256 \
      --operator-a-public /enrolled/operator-a.pem \
      --operator-a-pin TRUSTED_OPERATOR_A_PEM_SHA256 \
      --operator-b-public /enrolled/operator-b.pem \
      --operator-b-pin TRUSTED_OPERATOR_B_PEM_SHA256

Exit 0: both copies match the provided external pins and passed revalidation
in two rounds. Exit 1: missing, mismatched, malformed or untrusted copy
or enrollment. The report contains hashes and boolean flags only; it
never outputs signed envelope bytes or private key material.

## Security boundary and remaining limitations

Two different paths, even different parent directory inode IDs, are **not**
proof of different filesystems, physical machines, administrators or separate
administrative control. There are no real remote independent archives
deployed, and no remote attestation or independently persisted hash store.
Two rapid observations cannot exclude a malicious host controlling all
subsequent operations, a rollback of *both* copies with matching compromised
independent pins, or a deletion after the audit. It also cannot prove power-
loss durability, physical tamper prevention or witness-fence retirement.

The archive contains evidence of contradictory *signed claims*, not proof
that either checkpoint was actually committed to a keeper. No Nintendo
Switch game code or emulator work is changed by this stage.

All success reports keep false:
independent_operator_or_offhost_storage_proved,
independent_external_pin_retention_proved,
tamper_or_deletion_prevention_proved,
physical_durability_proved,
globally_latest_archive_proved,
either_branch_keeper_commit_proved,
automatic_cas_retry_authorized,
witness_fence_retirement_authorized,
witness_fence_retired,
native_switch_game_build_verified.
