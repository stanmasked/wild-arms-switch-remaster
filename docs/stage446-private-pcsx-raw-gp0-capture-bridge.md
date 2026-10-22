# Stage446 — practical owner-private raw GP0 capture bridge

## What is actually available in PCSX-Redux

The official PCSX-Redux documentation confirms a **GPU Logger**
(`Debug > GPU > GPU Logger`) that displays GPU commands and
VRAM-change visualizations, with frame replay and primitive
highlighting. The displayed logger is cleared when a new GPU
frame starts; such a "frame" may cover more than one v-sync if
the original PS1 program renders slowly.

See: https://pcsx-redux.consoledev.net/Debugging/gpu-logger/

**Important:** the current published documentation does **not**
confirm a raw, lossless, per-word GP0 file-export command or
endpoint from this GUI. The emulator's documented REST interface
supports raw VRAM but not a complete ordered GP0 wordstream.
Neither a GUI screenshot of logged commands nor a general CPU
trace is a drop-in replacement for ordered, complete raw GPU
packet bytes. Do not invent such an export or mark a GPU Logger
screenshot as an authentic complete raw packet trace.

A real end-to-end capture thus needs **separate owner-local
instrumentation of the original PCSX-Redux build or another
trusted GP0 source**. No original game trace has been acquired
in this development environment. This stage supplies the
**receiving/parser side** of that bridge with exact boundaries
and strict fail-closed validation.

## Raw input contract for an independently instrumented GPU

The owner-local instrumentation must output one binary file:
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
- Do not assume PCSX-Redux's GUI GPU Logger exposes this raw
  binary export automatically. A separate trusted recorder
  callback would be required, and needs independent
  implementation and testing against a pinned emulator revision.
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

## Reproducible next engineering gate

1. Identify and pin an exact PCSX-Redux revision, inspect the
   implementation of the GP0 data-entry path and decide where
   a recorder would capture **all** CPU/DMA-submitted words,
   including image payload words.
2. Add a carefully scoped **local only** instrumentation hook
   in a private/research emulator build to write the stream.
   Ensure start/end boundaries and synchronized pre/post VRAM
   are captured independently, without mixing frames.
3. Validate the hook against synthetic GPU fixture programs,
   comparing the GPU Logger's per-command sequence against
   the bytes received by Stage446; investigate unsupported
   commands explicitly instead of auto-approving them.
4. Only then load the owner's original Wild Arms disc and
   compare real Surf Village source→A0→80→texture/CLUT
   evidence against actual original framebuffer crops.

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
