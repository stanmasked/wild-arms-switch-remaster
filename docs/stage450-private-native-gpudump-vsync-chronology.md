# Stage450 — verify native PCSX GPU dump VSync chronology and final frame boundary

## Motivation

Stage447 imports the FIRST completed native frame from the official
PCSX-Redux `PSXGPUDUMPv1r1` format, and Stage448 checks transport
record counts even when GP0 commands beyond the current model appear.
Stage449 independently verifies that saved one-megabyte pretrace VRAM
and first-frame GP0 JSONL still match the original native source.

**None of these guarantees a whole native capture ends at a frame
boundary or that VSync cycle stamps were ordered.** A dump can contain
a complete first frame and also have an incomplete final frame,
repeated TraceBegin markers or malformed VSync chronology. A green
first-frame parser must not be mistaken for all-frame authenticity.

This Stage450 component is a **metadata-only timing/structure audit**
for the entire native dump, separate from 4bpp rasterization and
source-texture detection.

## Format and checks

The pinned PCSX-Redux upstream GPU Dumper records VSync as exactly
two u32 values, containing the low and high halves of a 64-bit
emulator GPU cycle counter:

```cpp
uint32_t stamp[2] = {uint32_t(cycle), uint32_t(cycle >> 32)};
packet(VSync, stamp, 2);
```

Official recorder source (pinned commit):
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.cc

`tools/audit_private_pcsx_native_vsync_chronology.py`:

- Reuses Stage447's strict native typed record parser: no
  truncated, unknown or oversized records are silently ignored.
- Checks there is exactly one **TraceBegin** and no VSync
  before it.
- Identifies each completed VSync-delimited live interval, and
  checks all successive 64-bit cycle stamps are **strictly
  increasing**. Zero or backward stamp differences are recorded
  as nonmonotonic, including around low-32-bit rollover.
- Allows an independent expected completed-frame count, if the
  operator has one, but never assumes an expected refresh rate.
  Cycle values are NOT seconds or wall-clock timestamps.
- Separately counts records and live GPU transport records after
  the last VSync, and records whether the very last typed record
  is actually a VSync. A trailing live record makes the **whole
  dump** unsafe to describe as ending on a completed frame.
- Supports a strict `--require-complete-vsync-end` flag to
  reject a non-monotonic, incomplete or miscounted file. Without
  the flag, the diagnostic still reports all faults without
  altering the owner's native dump.
- Caps the public-code report's sample of cycle differences at
  16 by default; all count/validity statistics still include
  every completed VSync interval.
- Reports *metadata only*: timing counts/deltas, SHA256, bounded
  errors and explicit caveats. **All metadata and hashes also
  remain strictly owner-private.** No original game identifiers,
  GP0 source words, VRAM, pixels, palettes or disc data are
  emitted.

The Stage448 preflight now contains `native_vsync_chronology`
alongside its existing first-frame subset compatibility result.
This is intentional: **a valid first frame does not validate
the whole native dump.**

## Private example

After the game owner locally records the original Wild Arms
scene with **Debug > GPU > Show GPU dump recorder / player**:

```sh
python tools/audit_private_pcsx_native_vsync_chronology.py \
  /private/WildArms/gpu/surf.gpudump \
  --expected-completed-frames 3 \
  --require-complete-vsync-end \
  > /private/WildArms/gpu/stage450-owner-private-chronology.json

python tools/preflight_private_pcsx_native_gpudump.py \
  /private/WildArms/gpu/surf.gpudump \
  > /private/WildArms/gpu/stage448-private-preflight-with-timing.json
```

The example count of three is *not* asserted for any current
original capture; operators must specify the actual expected
count from separately controlled recording conditions or omit
the flag entirely.

A VSync-boundary check does not attest the emulator executable,
disc image identity, game map, camera, audio synchronization,
texture/CLUT caches or real drawn framebuffer. Real source
verification still needs an original-game native capture,
Stage449 first-frame integrity and screenshot comparison
against the same scene/frame. Do not publish the original
GPUDUMP, extracted CDSTG, VRAM, rendered screenshots, stage
reports or hashes to public GitHub Actions.

## Synthetic test coverage

`tests/test_audit_private_pcsx_native_vsync_chronology.py`
adds **20 ROM-free regressions**, covering normal and multi-frame
recordings, 64-bit low-word rollover, equal and decreasing cycle
stamps, duplicated/missing TraceBegin, VSync before TraceBegin,
missing last VSync, trailing GP0 words, independent expected
frame counts, bounded diagnostic samples, file symlink protection,
strict mode and integration with the Stage448 preflight.

CI success verifies structural accounting for fabricated
native records, not a real PCSX-Redux capture of Surf Village
or any recovered Wild Arms original artwork.
