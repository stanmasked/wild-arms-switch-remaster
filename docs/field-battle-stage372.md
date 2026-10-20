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
