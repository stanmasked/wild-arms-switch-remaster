# Wild Arms Remake — Stage 372: fail-closed offline recovery destination

This is a small, isolated follow-up stacked on Stage371's independently
SHA-256-pinned, manual recovery tool. It does not modify the game's battle
logic, the existing CRC32 save format, or any PlayStation-derived assets.

## Risk and mitigation

- Reject a proposed staging output whose *resolved parent* is the live
  damaged journal's directory, or any descendant of that directory.
  A symlinked parent resolving into that directory is also rejected.
  This rejects even a dry-run: it is not presented as a safe recovery plan.
  Stage371 CI's separate staging root remains allowed.
- All journal inputs are read from file descriptors opened with O_NOFOLLOW
  where supported, then fstat-checked against the original lstat inode.
  A swapped symlink, different inode, special file or non-52-byte source
  must not be accepted. A trusted backup still requires a SHA-256 match,
  valid nested CRC32, schema and monotonic game counters.
- Reserve the output destination with atomic mkdir(0700) immediately before
  publication. The staged and fsynced directory is atomically renamed over
  *our own empty reservation* on POSIX, never a destination created by a
  different process after the earlier existence check. On failure, remove
  only our empty reservation and our hidden staging directory. Do not
  recursively remove any concurrently populated destination.

## Regression coverage

The Stage371 Python test fixture now stores live damaged files separately
from verified backup inputs and the output directory. Additional adversarial
tests cover dry-run and explicit staging refusal inside the live directory,
nested destinations, symlinked parent directories, accepted sibling
destinations, simulated failed publication with cleanup, competition for the
output directory and a backup swapped to a symlink before open.

The existing real NeXium guest25/guest26 experiment remains in the Stage371
base PR and must pass separately before claiming four restored wins, 32 EXP,
48 Gella, and retreat history across independent boots.

## Boundaries

Neither Stage371 nor Stage372 installs anything onto a running SDMC or
claims physical-card durability. A path restriction cannot prove a directory
is not part of some other live game installation; operators must select a
private external destination. Keep source files and trusted digests offline.

## Stage373 CI evidence hardening

The Stage371 Python test failed to import `WHITE` from
`audit_nexium_battle_double_corruption`; it belongs to
`audit_nexium_battle_corruption_warning`. The import is fixed on both
the parent PR and this stacked head. Earlier NeXium runtime steps never
executed because the import error stopped the smoke job at the unit
test gate. Nothing in that failed run proves or disproves guest25/26
reward persistence.

Stage373 also requires all four corrupted-source paths (archived A/B
and separately staged live A/B) to reference distinct inodes. This
prevents passing a byte-equality check by pointing both sides at the
same file or hardlink. Two adversarial oracle tests enforce the rule.

The separate `battle-save-offline-integrity.yml` workflow runs
source compilation, the offline file-staging tests and the screenshot
oracle's synthetic positive/adversarial tests on Python 3.11 and 3.13.
These are fast **synthetic** tests and cannot replace the real NeXium
guest trial. Do not mark restoration confirmed until the exact-head
NeXium run provides distinct process logs and real verified screenshots.

## Stage374 manifest/source chain of custody

The independent NeXium audit now checks the staged recovery manifest
against SHA-256 of **both** archived corrupted originals in addition to
the verified candidate. It enforces the expected offline staging kind,
`battle-progress.a` output name and explicit-manual-restore flag.

Three adversarial tests deliberately replace the manifest hash for slot A,
replace the hash for slot B, and falsely turn off the manual-only safeguard.
Each must fail the specific manifest/source binding check. This prevents
mistakenly reusing a good backup's manifest as evidence for unrelated
damaged source records.

The 27 filesystem cases and 19 synthetic screenshot-oracle cases give 46
distinct cases in the focused CI test suite. These are **test definitions**,
not a claim that CI or real NeXium guests passed.

## Stage376 offline staging publication durability

The staging tool already writes and fsyncs the recovered 52-byte WABJ file,
its manifest and the private staging directory. After the final same-filesystem
rename, it now also opens and fsyncs the **canonical parent directory** to
request persistence of the new destination entry. If parent fsync fails,
the operation raises an error rather than reporting a durable successful
publication. The complete already-renamed recovery package is preserved for
manual inspection; neither it nor any live damaged save is erased.

Two additional synthetic tests verify the fourth (parent-directory) fsync
and inject a failure specifically at that step, asserting that all source
bytes and both output artifacts remain unchanged and present.

There are now 29 offline staging tests and 19 synthetic screenshot/journal
oracle tests (48 total definitions). Even a passing host CI does not
prove real NAND/SD card power-loss durability, nor replacement on physical
Nintendo Switch hardware. The separate NeXium guest verification is still
necessary.

## Stage377 exclusive publish and Intel macOS validation

The previous staging implementation created a destination reservation
directory and used the ordinary POSIX rename. This could still overwrite
an unrelated **empty** directory if that name was replaced between
reservation and rename. Stage377 uses a kernel-enforced **exclusive
directory rename** instead:

- Linux: libc renameat2(AT_FDCWD, src, AT_FDCWD, dest, RENAME_NOREPLACE)
- macOS: libc renamex_np(src, dest, RENAME_EXCL)
- Unsupported platform/filesystem: **fail closed**, no unsafe rename fallback
- Embedded NUL bytes are forbidden before passing path bytes to ctypes.
- The destination parent remains fsynced after successful publication;
  if this final durability step fails the already-published package is
  preserved for manual examination without claiming full durability.

Linux smoke verification of the actual libc syscall confirmed that an
unrelated empty destination returns EEXIST and retains the staged
source, while publication succeeds for a previously absent name. This
is a local syscall smoke check, NOT a complete test of the Python
workflow, NeXium, or Nintendo Switch storage.

The focused synthetic regression suite now defines 32 filesystem tests
and 19 screenshot/journal tests (51 cases), including explicit races
against empty, populated and symlink destinations, plus a NUL-path
safety case. The GitHub Actions matrix tests Python 3.11 and 3.13 on
both Ubuntu x86_64 and macOS 15 **Intel x86_64**. Neither code coverage
nor the physical macOS runner result is assumed until the exact-head
CI has completed.

References:
- Linux renameat2 RENAME_NOREPLACE (kernel-enforced no replacement).
- Apple renamex_np RENAME_EXCL (macOS 10.12+, filesystem-dependent).

## Stage378 Linux/Darwin syscall contract regressions

Four synthetic tests now cover the **actual arguments** passed to the
native, no-replace directory publisher, rather than only exercising
filesystem behavior: Linux `renameat2` must receive `AT_FDCWD=-100`
for both directories and `RENAME_NOREPLACE=1`; Intel macOS
`renamex_np` must receive `RENAME_EXCL=4`. The unsupported-platform
case refuses a normal `rename` fallback; an EEXIST kernel response
becomes `FileExistsError` instead of a false success.

The exact test inventory is **36 offline filesystem cases** plus
**19 synthetic screenshot/journal cases** = **55 definitions**.
The Linux host syscall smoke (EEXIST for preexisting empty destination,
successful publish into absent name) was independently repeated on
2026-10-21. Apple-native implementation and real NeXium guest behavior
remain unconfirmed pending CI.

## Stage379 unsupported filesystem is a hard failure

The exclusive directory publisher deliberately does **not** downgrade to
ordinary POSIX rename if the filesystem reports `ENOTSUP`. This matters
on external or removable volumes: Apple's documentation makes
`RENAME_EXCL` conditional on volume support, and some macOS exFAT
filesystem implementations can reject that flag. The safe operational
choice is to select a separate output root on a filesystem supporting
exclusive rename (for example, an ordinary APFS volume), while keeping
the damaged SDMC originals untouched. No automatic fallback installation
or overwrite is attempted.

Two additional synthetic tests simulate native `ENOTSUP` separately on
Linux and macOS and require the staging directory and all its bytes to
survive, with no destination published. The focused suite now defines
**38 filesystem tests plus 19 screenshot/journal tests = 57 cases**.
macOS and Linux actual runner behavior remains unverified until CI finishes.
