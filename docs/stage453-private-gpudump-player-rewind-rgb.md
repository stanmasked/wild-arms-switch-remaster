# Stage453 — pixel-accurate GPU Dump Player **rewind** ROI witness

## Problem and scope

Stage452 checks the 1 MiB VRAM state in a paused screen witness
against the **initial VRAM embedded in a native GPU dump**.
A matching hash only means matching memory. There still is no
verified link between the screen shown on the host and the specific
live GP0 frame drawn later by the original Wild Arms.

The **native PCSX-Redux GPU Dump Player** provides a useful new,
more directly testable intermediate state: when the Player loads
and rewinds the dump, it recreates the **pre-recording VRAM**.
The pinned GUI renders an unscaled VRAM image by expanding the
original PS1 5-bit R/G/B channels to 8-bit channel values via
simple `<< 3`, ignoring source bit15 in the displayed RGB.
It optionally crops to the native GP1(05) video start and GP1(08)
display-mode rectangle.

Upstream verified source:

https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/gui/widgets/gpudump.cc

The rewind framebuffer is the **PRETRACE state before executing
the first live GPU packet**. It is **not** the drawn result after
the native first VSync. That distinction is essential.

## New owner-private verifier

`tools/verify_private_gpudump_player_rewind_rgb.py` compares
an **owner-provided, unscaled, no-filter, unmodified PNG patch**
from the Player's rewind VRAM view against the **exact bytes of
the original pretrace VRAM from the same native dump**:

1. Re-runs Stage451's native GPUDUMP, GPU GP0 packet, full 1 MiB
   VRAM and VSync-integrity binding, rejecting any inconsistent
   imports or unverified trailing native capture by default.
2. Takes an explicit (x,y,width,height) rectangle in the
   Player's **1024×512 raw VRAM pixel coordinates**; requires
   the owner's PNG dimensions to equal that rectangle, with
   no resampling, screenshot-window decoration or alpha
   transparency.
3. Converts the native pretrace VRAM's little-endian u16
   values by the exact pinned Player rule:
   `R=(word&31)<<3`,
   `G=((word>>5)&31)<<3`,
   `B=((word>>10)&31)<<3`.
   **Bit15 does not imply image alpha.**
   No 255/31 normalization, palette lookup, gamma remap or
   other guessed PS1 color interpretation is introduced.
4. Computes exact per-pixel RGB mismatch counts and bounded
   channel-error statistics, and compares the RGB SHA-256
   of the source VRAM ROI against the decoded PNG RGB bytes.
   The original graphic content and color values are **not
   included** in reports.
5. By default rejects *any* mismatch. Optional
   `--allow-rgb-mismatch` returns the diagnostic
   `REWIND_PNG_RGB_MISMATCH_NO_VISUAL_BINDING` with no visual
   match claim.
6. The opt-in `--require-native-display-window` option
   requires GP1(05)/GP1(08) restore state to be explicitly
   present and exactly match the expected full display crop.
   The crop follows the actual pinned GUI rules: display
   widths of 256/320/512/640 (or 368), and 240/480
   scanlines, constrained to a nonwrapping VRAM rectangle.
7. Optional independently supplied PNG and native dump SHA-256
   values guard against accidentally switching evidence files.
   The Player UI cannot independently attest the actual PNG
   export, so this remains a **conditional pixel-equality
   check**, not a same-frame witness.

## Owner-local verification workflow

After recording Wild Arms on a private machine with
PCSX-Redux **GPU Dump Recorder / Player**, save the native
`PSXGPUDUMPv1r1` file. Use Stage447's native importer to
produce its initial VRAM and first-frame GP0 JSONL. Verify
Stage451's exact import/chronology checks.

Then open **Debug > GPU > Show GPU dump recorder / player**,
load that same native dump, click **Rewind**, turn off
**Display area only**, and take a lossless PNG screenshot
of an **unscaled exact RGB crop of the raw 1024×512 VRAM view**,
excluding the Player window chrome, scaling and any canvas
background.

For example, if the privately extracted crop measures
32×24 pixels and starts at VRAM coordinate (100,60):

```sh
python tools/verify_private_gpudump_player_rewind_rgb.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/surf-first.before.u16le.bin \
  /private/WildArms/gpu/surf-first.gp0.jsonl \
  /private/WildArms/gpu/rewind-roi-100-60-32x24.png \
  --x 100 --y 60 --width 32 --height 24 \
  > /private/WildArms/gpu/stage453-private-rgb-state.json
```

These are example coordinates and paths; no genuine original
capture is asserted to exist.

For `--require-native-display-window`, capture the **entire
display-only crop** without any scaling, and use the exact
GP1-derived VRAM rectangle as the four coordinate arguments.

## Important limitations

- **No genuine Wild Arms GPU dump, Player screenshot or
  Surf Village frame has been obtained in this session.**
- A fabricated, hand-edited or unrelated PNG could match
  the same static VRAM region. This tool cannot prove the
  owner PNG really came from the native GPU Dump Player.
- A rewind pixel match is not a GPU first-frame render.
  The first frame's GPU drawing, native GP1 transitions,
  texture/CLUT caches, bit15/STP, clipping and final visible
  framebuffer must be checked separately.
- A PS1 15-bit VRAM preview is not necessarily the same
  output as the emulator's `/api/v1/screen/still` endpoint;
  do not silently conflate them or rescale to force equality.
- Original disc, CDSTG, native GPUDUMP, VRAM, PNG patches
  and **even hashes/metadata reports** remain owner-private,
  outside public GitHub and CI.

## Tests

`tests/test_verify_private_gpudump_player_rewind_rgb.py`
contains **22 ROM-free synthetic regressions**, including
zero/mismatched pixels, 5-to-8-bit conversion, high bit15,
nonzero VRAM row offsets, no scaling/alpha support,
independent PNG SHA-256 check, GP1 display window geometry,
missing/duplicate GP1 state, nonwrapping boundaries, file
symlinks, expected native SHA/frame mismatch and metadata
privacy.

**Accept only exact equality as conditional rewind-state
evidence. Do not call any original Surf Village artwork
restored on the strength of this stage.**
