# Stage454 — first GPU Dump Player Step: owner-private postframe visual witness

## Verified upstream behavior

In PCSX-Redux at pinned upstream revision
`de4a33e9a69abec4f567ae33567537f867dc2bba`,
`GPUDumpPlayer::rewind()` restores the initial GPU/VRAM state
from the native dump; `GPUDumpPlayer::step()` executes typed
GP0/GP1 events until the first native VSync and increments
`player->frame()` from zero to one. The Player GUI then calls
`player->gpu()->getVRAM()` and expands its PS1 RGB555 pixels
to RGBA using the explicit formula documented in Stage453.

Pinned upstream sources:

- https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.cc
- https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/gui/widgets/gpudump.cc

The stock Player GUI exposes Play/Pause, Step, Rewind and a VRAM
preview. **There is no verified stock GUI button to export the
complete 1MiB VRAM of the detached GPU after Step.**
The `/api/v1/gpu/vram` endpoint belongs to the live emulator
rather than automatically selecting the detached GPU of the
GPU Dump Player. Do not assume it is a post-Step Player export.

## New verifier

`tools/verify_private_gpudump_player_first_step_rgb.py` accepts
five **independent owner-private artifacts**:

1. Native `PSXGPUDUMPv1r1` capture;
2. Stage447 imported initial VRAM (1,048,576 bytes);
3. Stage447 imported first-frame GP0 JSONL;
4. **Operator-supplied after-first-Step detached GPU VRAM**
   in native PS1 u16 little-endian order (1,048,576 bytes);
5. **Operator-supplied after-first-Step unscaled PNG ROI**
   from the Player's displayed 1024×512 VRAM.

It independently re-runs Stage451's native dump, initial VRAM,
GP0 and VSync integrity verification. It requires all five
paths to be distinct regular nonsymlink files, independently
accepts optional expected SHA-256 for native dump/post-Step
VRAM/PNG, and optionally checks the operator's Player frame
indicator is **exactly 1**. This indicator is *operator
reported*, not extracted or authenticated by the dump.

The Stage453 pixel routine checks the operator PNG ROI against
the **post-Step VRAM**, not the initial Rewind VRAM. It uses
the pinned Player RGB conversion (5-bit components shifted
left by three, ignoring bit15 in visible color) and rejects
any pixel mismatch by default. If a diagnostic-only
`--allow-rgb-mismatch` is provided, the report explicitly
says no visual binding is supported.

The verifier also compares initial and post-Step VRAM
independently, reporting:
- changed whole-VRAM u16 halfword count;
- changed u16 words in the requested ROI;
- **visibly changed RGB555 ROI pixel count** (ignoring bit15);
- whether post-Step VRAM is identical to the initial snapshot.

`--require-changed-roi` can reject a fully static ROI for
specific experimental captures, but is not a correctness
requirement: genuine graphics may leave a region unchanged.
`--require-native-display-window` verifies the exact
GP1(05)/GP1(08) full display crop from pretrace state; this
subset of the Stage447 importer rejects live GP1 commands
before first VSync, so the supported first frame has no
modeled display-window changes.

Two possible statuses:
- `POST_STEP_ONE_RGB_EQUALITY_UNATTESTED_PLAYER_SNAPSHOT`
- `POST_STEP_ONE_RGB_MISMATCH_NO_VISUAL_BINDING`

## Critical remaining proof gap

The stock Player's **Step** renders the first frame with its
own detached **software GPU**, but Stage454 does **not** extract
that software GPU's VRAM itself or attest the origin of the
user-supplied PNG. There is therefore no independent proof
that either post-Step file came from the actual GPU dump.
A perfect RGB match only proves that **those two supplied
post-Step surfaces agree** and that the initial native capture
passes the earlier integrity gates.

To obtain stronger evidence, we must next implement or
verify a **trusted, owner-local export of detached Player GPU
VRAM and exact Step=1 identity** in a pinned emulator build;
then directly compare its exported RGB against the same
Player frame and original Surf Village screenshots. A
pretend GPU rendering result assembled from synthetic bytes
is not a substitute.

No original Wild Arms BIN/CUE, CDSTG, GPU dumps, screenshots,
VRAM snapshots, source graphics or **private hashes/reports**
may be committed to public GitHub.

## Owner-private example

Only after the original game is available locally, an
authentic native dump has been saved, and an independently
verified owner-local way to export the Player's detached
post-Step VRAM is available:

```sh
python tools/verify_private_gpudump_player_first_step_rgb.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/surf.before.u16le.bin \
  /private/WildArms/gpu/surf.frame0.gp0.jsonl \
  /private/WildArms/gpu/player-step1.vram.u16le.bin \
  /private/WildArms/gpu/player-step1-roi.png \
  --x 100 --y 60 --width 32 --height 24 \
  --expected-player-frame-label 1 \
  > /private/WildArms/gpu/stage454-postframe.private.json
```

These paths and coordinates are illustrative; there is **no
authentic Wild Arms GPUDUMP or post-Step export** in this
development session.

## Synthetic validation

`tests/test_verify_private_gpudump_player_first_step_rgb.py`
contains **14 ROM-free scenarios**: changed/unchanged frame
state, RGB555 bit15-only changes, stale rewind screenshot,
required changed ROI, false Player frame label, private
hash matching, mutated native GP0, short postframe raw VRAM,
PNG dimension mismatch, GP1 display-region constraint,
multi-frame native dump first-Step selection and privacy.

This stage preserves scientific honesty: conditional
post-Step RGB equality **is not a completed original
game scene reconstruction**.
