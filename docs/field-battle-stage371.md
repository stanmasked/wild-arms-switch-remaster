# Wild Arms Remake — Stage 371: verified external battle save recovery

Stage369 verified that two damaged WABJ slots fail closed without claiming
missing progress was restored. Stage370 displays a manual ZL warning.
Stage371 adds an OFFLINE tool to prepare one previously saved, independently
verified backup in a NEW staging directory. It never installs automatically.

## Safety model

The operator supplies the two 52-byte corrupted battle journal files and
one or two separate backup candidates, each accompanied by a previously
recorded independent SHA-256. The offline tool validates:
- Source files are distinct physical files, not symlinks or hardlink aliases.
- Both live copies are invalid, whereas the candidate backups have genuine
  WABJ v1 / WABR v1 structure, reserved bytes, valid inner and outer CRC32,
  permitted battle outcomes and sane cumulative counters.
- The selected raw backup matches its pinned SHA-256 byte for byte. If two
  backups are provided, choose highest generation, but reject conflicting
  equal-generation copies or an unexplained regression of accumulated wins,
  losses, retreats, EXP or Gella.
- An output directory may not already exist. The default is dry-run.
  Explicit --execute is required to create a new private staging directory
  containing an unchanged battle-progress.a and a JSON provenance manifest.
  The staged file is checked after writing, and live damaged sources are
  checked for unintended changes.
- No live SDMC file is deleted, renamed, opened for writing, or installed;
  no second valid copy is fabricated, and nothing is imported from a ROM.

### Example

This invocation is dry-run, with no output files produced:

    python3 tools/stage_verified_battle_backup.py \
      --damaged-a /saved-sdmc/battle-progress.a \
      --damaged-b /saved-sdmc/battle-progress.b \
      --backup-a /independent-backups/known-good-a.bin \
      --backup-b /independent-backups/known-good-b.bin \
      --sha256-a ORIGINAL_PINNED_A_SHA256 \
      --sha256-b ORIGINAL_PINNED_B_SHA256 \
      --output-dir /isolated-recovery/never-existing-output

Only after reviewing the hashes and counters should an operator repeat
the command with --execute. Never point it to an active game directory.
Installation, if desired, is a separate user-authorized operation requiring
immutable preservation of the original corrupt saves.

CRC32 detects accidental corruption and SHA-256 identifies exact bytes,
but neither authenticates a backup without a trustworthy hash obtained
independently before the failure. A pair of malformed saves contains
insufficient evidence to reconstruct an unknown original progress state.

## Verification design

Twenty synthetic positive/adversarial tests cover selected generation,
reward preservation, dual CRC validation, pinned SHA-256, malformed backup
semantics, conflicting generations, symlink/hardlink rejection, output
collisions, dry-run and no writes to damaged files. An additional 14
synthetic image/journal oracle tests challenge fabricated wins, false
warnings, duplicate rewards, modified journal generation and PID reuse.

The experimental NeXium workflow replays previously verified stage365–370
through two simultaneous CRC-corrupted journal copies, then:
1. Uses the already independently validated stage368 JSON SHA-256 values
   as external trusted pins to explicitly stage original intact gen5/gen6
   WABJ copies from before stage369 fault injection.
2. Copies only the exact validated gen6 A into a new isolated NeXium SDMC.
   The original damaged Stage369 root is never touched.
3. Real guest25 must restore exactly four victories, two retreats,
   32 prototype EXP and 48 prototype Gella, without a false corruption
   warning. One B-retreat commits gen7 B with four victories,
   three retreats and unchanged EXP/Gella.
4. Real independent guest26 must reload those same earned rewards and
   retreat history without creating new journal bytes.
5. A read-only audit compares the actual Xvfb images, both WABJ records,
   PID labels, strict controller key edges, preserved original field map,
   and byte-for-byte unchanged source corrupt A/B.

This is a ROM-free placeholder battle economy and an emulator-only test
using a nonstandard NeXium loader probe, NOT original PlayStation economy,
physical Nintendo Switch SD card durability, or an automatic recovery
feature.
