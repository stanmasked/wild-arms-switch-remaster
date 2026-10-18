# Stage 270 — libnx software-framebuffer field prototype

This new `switch/` target adapts the synthetic gameplay core from stages
265–269 into a native Nintendo Switch **homebrew NRO** build target, isolated
from host CMake. The repository does **not** include a compiled NRO by default.

The frontend uses the current libnx `NWindow` + `Framebuffer` API at
1280×720 in double-buffered linear RGBA8 mode, and the `PadState` HID API.
An original 11×7 ASCII test map is shown as coloured 64×64 rectangles,
including walls, floor, event and exit tiles. A red square marks the
character and a small dark rectangle indicates facing. A narrow top stripe
turns amber when an event/exit needs acknowledgement; pressing **A**
acknowledges it. Use **D-pad** or **left stick** to move, and **+** to exit.

Each update samples the hardware counter and passes a bounded integer
millisecond delta through `advance_pad_frame`. The Switch stick's +Y-up
axis is inverted for the core's +Y-down field convention. Time elapsed
during long applet pauses is intentionally clamped to 1000 ms instead of
letting the character jump many steps after resume.

## Build

Install devkitPro's `switch-dev` toolchain and ensure `DEVKITPRO` points to
its installation. Then run:

```sh
make -C switch
```

The output should be `switch/wild_arms_field.nro` after a successful build.
The independent GitHub Actions workflow `Switch field prototype` attempts
the same build inside `devkitpro/devkita64` and publishes the NRO only if it
passes. Do not treat presence of a workflow or source code as proof that a
binary was built or ran on hardware.

## Constraints

- No original Wild Arms sprites, maps, CD/BIOS, music, scripts, or other
  copyrighted game assets are used or uploaded.
- This tests an **original synthetic** walkable map, not the original game's
  field, battle, event or camera engine.
- Gameplay is tile-by-tile, not pixel-interpolated walking.
- There is no original PS1 asset loader, original-compatible save format,
  or battle system. Later stages added synthetic NeXium field captures and
  experimental SD-backed field saves, but no physical Switch validation.
- The standalone `switch/source/field_core.cpp` includes the canonical
  `src/field.cpp` once, avoiding a divergent field logic implementation.
- CTest remains the authoritative host-level correctness check; the NRO
  build workflow proves cross-compilation only when green.

## Next verification

Verify native compilation in CI; inspect actual gameplay in a Switch
homebrew-compatible emulator or personal Switch; compare key orientation,
frame pacing, display output, suspend/resume, and event acknowledgement.

## Stage 291 — volatile manual quicksave

In **manual** field mode, press **Y** to remember the current complete
world/player/event/controller state in an in-memory slot, then **− (Minus)**
to restore it. Saving or restoring consumes one update without moving or
acknowledging a pending event. An empty slot does nothing, and a malformed
snapshot is rejected before replacing the live state. Both controls are
ignored during scripted autoplay (X); after B resets manual exploration,
the in-memory checkpoint remains available.

This is **not** a persistent game save. The slot is lost when the NRO exits
or the console closes the process. No Wild Arms original save data or game
files are read/written. The five established NeXium autoplay reference
frames and their pixel parity contract are deliberately unchanged.

## Stage 293 — versioned field save record (portable host codec)

The host/Switch-neutral \`include/field_save_codec.hpp\` introduces a fixed
40-byte v1 record for the *synthetic* manual field state. It encodes map
identity, location, facing, movement counter, movement-clock state, active
trigger and confirm-button decoder using fixed-width little-endian fields.
An explicit 32-bit CRC detects accidental byte corruption; an independent
64-bit world fingerprint rejects saves from incompatible synthetic maps.
Reserved fields, unsupported versions, malformed coordinates/clock/pending
events and truncated or extended records are rejected **without modifying
the live player or the previous destination state**. It uses no proprietary
Wild Arms save data.

This is a **serialization library only**. Stage 293 does **not** write to
the Nintendo Switch SD card, add persistence between process launches, or
change Y/Minus quicksave behavior. These require a future platform-specific
file adapter with atomic replacement and failure recovery. The synthetic
five-scene reference PNGs, known NeXium guest visuals and valid NRO layout
remain unchanged.

\`wa_field_save_codec_tests\` is included in Host/Matrix CTest coverage.

## Stage 294 — experimental SD save integration

The Nintendo Switch homebrew build now attempts an SDMC mount with
`fsdevMountSdmc` (reuses an existing `sdmc` device), and creates its own
`sdmc:/switch/wild_arms_field/` directory. The synthetic game uses two
generational files, `field-save.a` and `field-save.b`. **Y** still creates
its normal in-RAM snapshot; after the gameplay frame succeeds, it also
writes a generation to SD when the directory is accessible. The writer
generates a verified 56-byte record containing the Stage-293 40-byte
versioned state, and updates the *other* slot using a temporary file,
flush, `fsync`, close, read-back verification, and rename. It does not
unlink the currently newest validated save. **Minus** uses the same
original RAM quickload; if RAM has no snapshot (e.g. a new app launch),
it imports the most recent validated SD generation before drawing.
A corrupt latest slot may fall back to a valid older generation.

**Important limitations:** SDMC may be unavailable (notably in
emulators). If it is unavailable or a file write fails, RAM quicksave
continues but there is **not yet a user-visible disk-write success/failure
indicator**. There is no claim of full SD FAT/exFAT power-loss atomicity,
durable directory metadata, concurrent-process writer protection, or
tested persistence across two native Switch hardware sessions. The
journal provides recoverable independent generations in normal tested
file-system failure scenarios, not a guarantee for sudden hardware
power loss. No original game content is written. The existing five
autoplay and eight NeXium manual screenshots are unchanged.

Host `wa_field_save_file_tests` exercises normal load, journal generations,
corrupt-latest fallback, stale temporary files, blocked replacement,
world mismatches, and generation exhaustion. The Switch NRO must be
cross-compiled separately and manual SD persistence must be verified
on an actual console before being called hardware-confirmed.
