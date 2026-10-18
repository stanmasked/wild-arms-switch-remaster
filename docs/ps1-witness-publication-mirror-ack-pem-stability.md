# Stage 264W — enrolled Ed25519 public key stability throughout offline replay

Stage 264U preserves full signed mirror-acknowledgment histories in a private
archive, and Stage 264V checks the archive's file identity and exact bytes
before and after complete memory-only replay. Stage 264W extends the **same
default Stage 264U inspect path** to both enrolled operator public PEM files.

## New checks

Before opening the archive, the inspector observes **both** public PEMs:
owner-private 0600 single-link regular files under private 0700 parent
directories, exact bounded bytes (maximum 4096 bytes), device and inode,
size, ownership, permissions, nanosecond mtime and ctime. Files are
opened with O_NOFOLLOW and validated against their path identities
before/after reading.

After reconstructing both full SQLite nonce histories and verifying
every completed Ed25519 acknowledgment, the inspector validates that:

1. The SHA-256 of **each** original public PEM exactly matches the
   operator's enrolled PEM pin recovered from its genesis-SHA-256-pinned
   private archive history.
2. A newly opened read of each PEM has the exact same bytes and filesystem
   identity as at the beginning of the audit.
3. The archive itself remains unchanged under Stage 264V's previous
   full audit interval check.

Crucially, the operator who has **no completed signature** in the
archived history still has an enrollment; their public PEM must pass
the exact same pin and stability checks. A key cannot be replaced
partway through the audit just because that role was pending or unused.

The same validation applies when Stage 264U **creates** an archive,
because archive creation requires an independent final inspect/readback.

## Regression coverage

    python3 -m unittest discover -s tests -p test_record_witness_publication_mirror_ack_pem_stability.py -v

The synthetic suite replaces key PEM files with new inodes holding the
same bytes, rewrites in-place, truncates, unlinks, swaps a symlink,
introduces an extra hardlink, relaxes permissions and substitutes the
wrong enrolled operator's otherwise valid PEM. Each mutation is
performed at a deterministic point after replay and before a
successful verifier response.

The suite also confirms offline replay without source SQLite files
and checks the continued explicit negative claims for external
operator custody, external archive-pin retention, global CAS,
automatic merge/retry, witness-fence release and Switch game builds.

## Limitations

These are **local filesystem race defenses**, not proofs of off-host
key custody, hardware-backed key enrollment, remote WORM retention,
honest operator identity or globally consistent independent nonce
allocation. A privileged actor who can change the filesystem outside
the observed interval may still bypass local checks. Separately
retained trusted external enrollment SHA-256 values are mandatory.
No remote deployment, automatic registry repair, witness-fence
retirement or native Nintendo Switch gameplay is implemented.
