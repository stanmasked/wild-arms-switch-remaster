# Stage446 — practical owner-private raw GP0 capture bridge

## What is actually available in PCSX-Redux

The official PCSX-Redux documentation confirms a **GPU Logger**
(`Debug > GPU > GPU Logger`) that displays GPU commands and
VRAM-change visualizations, with frame replay and primitive
highlighting. The displayed logger is cleared when a new GPU
frame starts; such a "frame" may cover more than one v-sync if
the original PS1 program renders slowly.

See: https://pcsx-redux.consoledev.net/Debugging/gpu-logger/

**Updated upstream-source verification:** PCSX-Redux at pinned
commit `de4a33e9a69abec4f567ae33567537f867dc2bba` includes
a **separate native GPU Dump Recorder / Player**. The GUI exposes
`Debug > GPU > Show GPU dump recorder / player`, then
`Start recording...` / `Stop recording`. Its native file records
typed GP0/GP1 packets, v-sync boundaries, initial full VRAM and
GPU state, starting at an idle GP0 boundary on the next v-sync.

Verified upstream implementation:
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.h
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/gui/widgets/gpudump.cc

**The Stage446 raw-u32le adapter is NOT the native dump reader.**
The native file is a `PSXGPUDUMPv1r1` typed packet container,
not a flat GP0 stream, and its initialization contains a full
1 MiB VRAM upload (larger than Stage437's per-packet limit).
For compatible emulator builds, a separate Stage447 native-format
reader is preferable to writing a custom GPU recorder.
The remaining Stage446 tool is intentionally retained only for
already available independent *flat* GP0 u32le recordings.

No actual original Wild Arms GPU dump has yet been captured
in this environment; native capture availability is verified
from **upstream source**, not from an original-game run.

## Raw input contract for an independently instrumented GPU

For the Stage446 **legacy flat-stream adapter only**, an independent
instrumentation source must output one binary file:
`original-gp0.u32le`.

- Every **32-bit word passed into the PS1 GPU's GP0 data command
  processor**, in the exact emulator-consumed order.
- Stored as an unsigned little-endian `uint32_t` word. A GP0(A0)
  image's data words are included in full; never interpret their
  upper eight bits as new opcodes.
- The start of the recorded stream must be at a **complete GP0
  packet boundary**; the recorder must capture raw VRAM **before**
  the first recorded GPU command. A mid-packet start cannot be
  repaired by this adapter.
- Stop only after the complete final command, and capture the
  post-stream VRAM *after* its completion with no unrecorded
  writes. A raw stream ending at a syntactically valid packet
  boundary does not, by itself, prove the full frame was
  captured. Independent emulator instrumentation must record
  begin/end conditions and frame identity.
- Do not mistake the ordinary GPU Logger GUI for a flat binary
  exporter. On pinned newer upstream PCSX-Redux, use the **native
  GPU Dump Recorder** instead and a separate typed-dump adapter.
- In particular, `-trace` is documented as **CPU** trace
  logging, not GP0 packet export; do not confuse the two:
  https://pcsx-redux.consoledev.net/cli_flags/

The existing Stage432 paused screenshot/CD witness remains useful
for **visual scene inspection** but is not an authenticated
pre-command VRAM + raw GP0 capture pair.

## What Stage446 implements

`tools/package_private_raw_gp0_wordstream.py` reads only the
owner-provided **raw little-endian GP0 wordstream** and the separate
exactly **1,048,576-byte prepacket VRAM**. It reconstructs
packet boundaries for the *supported subset* of the Stage437–445
model:

- GP0(E1/E2/E3/E4/E5/E6), GP0(00/01): single words;
- GP0(20h–3Fh): fixed-size polygon packets, using the actual
  textured/Gouraud/quad flags;
- GP0(60h–7Fh): fixed-size rectangle packets, including the
  variable-width form;
- GP0(80h): source→destination VRAM copy, four words, strict
  nonoverlap/VRAM boundary checks;
- GP0(A0h): three-word header plus exactly
  `ceil(width × height / 2)` raw pixel words. The extra high
  halfword when the pixel count is odd is part of the raw packet
  but is not an additional command.

GPU(E6) write-mask-disabled state must be explicitly present
before transfers; unsupported mask changes fail. Unmodeled
commands (including fill, polyline and VRAM read) **fail closed**.
A complete original game frame containing an unsupported
command will be **rejected rather than silently truncated or
partially replayed**. This is a current model restriction, not
evidence the original game is malformed.

The private adapter verifies all packet boundaries and a
strict **4 MiB input cap**, an exact VRAM size and a maximum
20,000 packet count. It optionally matches a caller-provided
SHA-256 for the raw input and re-parses the generated
Stage437-compatible JSONL with the Stage437 validator before
saving it.

The resulting JSONL is created **only on the owner's machine**,
with no-clobber semantics and restrictive 0600 permissions. No
original GP0 packet words or source-color values are printed
in the metadata. The private hashes are also sensitive and
must not be uploaded to public GitHub or CI.

## Owner-local example after trusted instrumentation exists

```sh
# Paths are illustrative; the GP0 recorder is NOT implemented here.
python tools/package_private_raw_gp0_wordstream.py \
  /private/WildArms/gpu/original-gp0.u32le \
  /private/WildArms/gpu/before-first-gp0.u16le.bin \
  /private/WildArms/gpu/complete-packets.jsonl \
  --frame 42 \
  > /private/WildArms/gpu/stage446-private-packetizer-metadata.json

# Only after extracting the original CDSTG locally (Stage435/436):
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/before-first-gp0.u16le.bin \
  /private/WildArms/gpu/complete-packets.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/after-last-gp0.u16le.bin \
  > /private/WildArms/gpu/stage446-private-vram-clut.json
```

No such owner-local raw capture has yet been obtained in this
session. The full original `Wild Arms (USA).bin` also remains
out of reach of the connected Google Drive per-file download
limit, and it has not been analyzed end-to-end.

## Reproducible next engineering gate (updated)

1. Use a PCSX-Redux build containing the pinned native GPU
   Dump Recorder; verify the GUI record/playback path locally.
2. Decode the native typed dump format with a strict Stage447
   adapter: extract pre-trace full VRAM, skip initialization,
   and preserve the *live* complete GP0 stream up to the first
   v-sync. Reject unsupported live GP1/readback commands.
3. Reconstruct the Stage437 private JSONL and compare a dump's
   original preamble/state/frames against PCSX-Redux's own GPU
   Dump Player. Unsupported commands must fail closed.
4. Then use an owner-private Wild Arms disc to record Surf Village
   and compare real source→A0→80→texture/CLUT evidence against
   original screenshot crops. Never publish the dump or assets.

The emulator codebase carries GPL obligations; if distributing
a modified emulator, comply with its license. This PR itself
does not embed upstream emulator source, game assets or BIOS.

## Synthetic CI

`tests/test_package_private_raw_gp0_wordstream.py` adds
**28 ROM-free tests**: mixed transfer/draw packet streams;
GPU image words whose high byte resembles an opcode; odd
pixel padding; missing E6 and unsupported mask states;
unsupported primitives; malformed copy bounds/overlap;
truncated A0 headers and payloads; missing final word;
incomplete polygon; maximum supported transfer sizes;
strict Stage437 JSONL roundtrip; existing-output refusal;
correct and incorrect SHA; invalid prepacket VRAM geometry;
symlink protection; file permissions and no raw bytes
in the metadata.

A green test suite proves the receiver/validator handles
invented input. **It is not proof of authentic original
PCSX-Redux GP0 capture or completed Wild Arms scene art.**
