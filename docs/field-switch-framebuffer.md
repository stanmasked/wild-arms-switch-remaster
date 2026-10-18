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
- There is no PS1 asset loader, no game save, no battle system, no published
  emulator capture and no verified real-device execution.
- The standalone `switch/source/field_core.cpp` includes the canonical
  `src/field.cpp` once, avoiding a divergent field logic implementation.
- CTest remains the authoritative host-level correctness check; the NRO
  build workflow proves cross-compilation only when green.

## Next verification

Verify native compilation in CI; inspect actual gameplay in a Switch
homebrew-compatible emulator or personal Switch; compare key orientation,
frame pacing, display output, suspend/resume, and event acknowledgement.
