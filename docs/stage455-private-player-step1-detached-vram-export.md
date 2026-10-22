# Stage455 — owner-local detached GPU Dump Player Frame 1 VRAM export

## Why this is needed

The upstream PCSX-Redux GPU Dump Player uses a **detached software GPU**. Its
`GPUDumpPlayer::step()` consumes native GP0/GP1 records until the first VSync
and advances the Player frame label from 0 to 1. Stage454 can compare
operator-supplied post-Step VRAM with a PNG, but until now neither was
exported or labeled by a trusted **same-call** GPU Player operation.

This stage supplies a **pinned-upstream patch generator**, a small versioned
snapshot transport, and a standalone verifier. It does **not** modify a
public PCSX-Redux installation in this environment.

## Pinned owner-local PCSX-Redux patch

The Python tool `tools/patch_private_pcsx_gpudump_player_step1_export.py`
accepts only a **clean checkout** of the upstream PCSX-Redux revision
`de4a33e9a69abec4f567ae33567537f867dc2bba`, with exact source
anchors in `src/gui/widgets/gpudump.h` and `gpudump.cc`.

Run `--check` to verify its patch against the owner-local checkout
without modifying files, or run `--apply` explicitly after checking:

```sh
python tools/patch_private_pcsx_gpudump_player_step1_export.py \
  /private/tools/pcsx-redux

python tools/patch_private_pcsx_gpudump_player_step1_export.py \
  /private/tools/pcsx-redux --apply
```

Then build this patched version of PCSX-Redux **locally**, following
upstream documentation and GPLv2-or-later obligations. This public
game repository does not vendor PCSX-Redux code, game BIOS, images
or original graphics. The generated patch touches only two GUI files
and is not claimed CI-compiled against the complete emulator here.

The added GPU Dump Player UI control:

- Is enabled only when playback is paused and `player->frame() == 1`.
- Reads exactly **1024×512×u16** from `player->gpu()->getVRAM()`, not
  the live emulator's `g_emulator->m_gpu`.
- **Copies the full snapshot immediately on button click**. The later
  Save dialog writes the frozen snapshot, so stepping or changing the
  emulator between button click and filename selection does not alter it.
- Encodes each 16-bit VRAM word explicitly in **little-endian** order.
- Uses an exclusive-create binary file mode (`wbx`) and sets
  owner-only file permissions before writing. It refuses existing paths
  and removes a failed partial output.
- Emits no real-world game source bytes in text logs; raw export is
  strictly an owner-local file and must never be attached to a public PR.

The export button is an **opt-in research build feature**. It does not
run on GitHub Actions and cannot be assumed to exist in stock binaries.

## Single-file format, v1

`tools/verify_private_gpudump_player_step1_export.py` accepts exactly
`32 + 1,048,576` bytes:

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 16 | Magic `WA1STEPVRAMv1` followed by three NULs |
| 16 | 8 | little-endian unsigned Player frame, **exactly 1** |
| 24 | 4 | little-endian VRAM byte count, **1,048,576** |
| 28 | 4 | little-endian CRC32 over the VRAM payload |
| 32 | 1,048,576 | u16le Player detached software GPU VRAM |

The Python reader rejects a wrong magic/version, wrong frame, wrong
length, truncated/trailing bytes and any CRC32 mismatch. CRC32
detects accidental corruption; **it is not a cryptographic
authentication** of the emulator or a native dump.

The verifier independently re-runs Stage451's original native GPUDUMP,
initial VRAM, first-frame GP0 and VSync integrity checks, then compares
the exact RGB555-derived screenshot patch to this **same exported
snapshot container**. It counts changed full-VRAM and ROI halfwords,
distinguishes bit15-only changes, supports independent SHA256 checks
and optional changed-ROI requirements, and never prints actual pixels.

The distinct report statuses are:

- `PATCHED_PLAYER_STEP1_CONTAINER_RGB_EQUALITY_DUMP_LINK_UNVERIFIED`
- `PATCHED_PLAYER_STEP1_CONTAINER_RGB_MISMATCH_NO_VISUAL_BINDING`

## Owner-local operation

After building patched PCSX-Redux, open the **same** native Wild Arms
GPUDUMP in the GPU Dump Player. Click **Rewind**, then **Step** once,
and verify the Player UI displays **Frame 1**. While playback is
paused, select **Export Step 1 private VRAM...** and save the
snapshot outside every public repository. Capture a lossless,
unscaled PNG ROI from the Player's `1024×512` VRAM preview.

The following paths and coordinates are **examples**, not existing
authentic original frames:

```sh
python tools/verify_private_gpudump_player_step1_export.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/first.before.u16le.bin \
  /private/WildArms/gpu/first.gp0.jsonl \
  /private/WildArms/gpu/player-step1.wa1step.bin \
  /private/WildArms/gpu/player-step1-roi.png \
  --x 100 --y 60 --width 32 --height 24 \
  > /private/WildArms/gpu/stage455-player-step1.private.json
```

## Remaining authentication gap

The snapshot format carries the **frame label and VRAM captured by the
same patched Player call**. This narrows Stage454's operator-only
provenance gap substantially.

**It does not yet embed a cryptographically authenticated identity of
the native GPUDUMP that was loaded into the Player.** Stage451
authenticates the separately provided native GPUDUMP and pretrace
import *against each other*, but cannot prove that this same dump
was the one loaded when the export button was pressed. The GUI build
itself is not attested by this repository, and an independently
supplied PNG is still an untrusted visual witness. A future step
should bind the loaded dump's content digest to the snapshot at source.

No real Wild Arms original-game GPU dump was recorded during this
stage. The original full BIN/CUE, CDSTG, GPU dumps, VRAM snapshots,
screenshots and **private hashes or reports** must remain outside
public GitHub or CI. No Surf Village roof, well, CLUT or geometry
is claimed to be visually recovered.

## Validation

`tests/test_verify_private_gpudump_player_step1_export.py` contains
**22 ROM-free synthetic tests** for binary header/frame/CRC32,
exact size, incorrect/altered fields, RGB equality and mismatches,
bit15, native GP0 consistency, expected digests, symlinks and
metadata privacy. It also tests that patch generation is restricted
to exact upstream GUI anchors and never selects the live GPU.

**These tests do not compile the complete upstream emulator
GUI patch.** A local pinned PCSX-Redux build and an original-game
native capture are still required.
