# Stage437 — PRIVATE GP0 timeline from preframe VRAM to draw-time CLUT observations

## Technical motivation

Stage428 can correlate a Surf Village candidate 16-color palette row
with a GP0 textured draw CLUT address **in a post-frame VRAM dump**.
This establishes only a memory occurrence *after* GPU operations:
palette bytes may be overwritten between the draw and the captured
dump, and the GPU texture/CLUT cache can retain colors.

Stage437 handles a narrower, falsifiable problem: **given a separately
instrumented complete ordered GP0 packet trace and a VRAM snapshot
taken before the first packet, how do supported CPU→VRAM / VRAM→VRAM
transfers change candidate CLUT memory prior to each draw command?**

Official GP0(A0)/GP0(80) memory-transfer command contracts:
https://psx-spx.consoledev.net/ps1/gpu/memory-transfer-commands/

GP0(E6) can modify mask-bit protection for VRAM uploads and GPU blits,
so Stage437 **requires an explicit GP0(E6) mask-disabled command before
each A0/80 transfer** (or earlier in the same trace). If masking is
enabled or no mask state was observed, transfer replay fails closed.
Reference: https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/

## What Stage437 actually supports

`tools/audit_private_gp0_upload_timeline.py`:

- Inputs: owner's private Surf Village `CDSTG.BIN`, **1,048,576
  bytes** raw *PRE-trace* PS1 VRAM (not the post-frame Stage429 snapshot),
  and an **independently obtained ordered and completely packetized**
  private GP0 JSONL trace;
- Requires trace header's `initial_vram_sha256` to equal the actual
  source snapshot SHA-256. Rejects malformed records, duplicate keys,
  mixed frames, oversized traces and unknown commands;
- Accepts GP0(A0) CPU→VRAM image transfer with all data halfwords,
  including mandatory padding for odd pixel counts;
- Accepts GP0(80) VRAM→VRAM copy when both rectangles are entirely
  inside conventional 1024×512 VRAM and **do not overlap**;
- Requires explicit GP0(E6) value zero for transfer mask state;
- Uses already tested Stage428 command decoding for the supported
  textured polygons and rectangles, state commands and untextured
  polygon/rectangle draw commands; **all other GP0 opcodes fail
  closed** (including GPU framebuffer fill GP0(02));
- Records every supported 4bpp textured draw's CLUT coordinate,
  pre-draw row SHA-256, source bank+row candidate matches, texture
  page coordinates and an explicitly conditional row-rewrite flag;
- The flag is true only when **all 16 palette halfwords were
  explicitly rewritten through modeled transfers since the preceding
  draw packet**. Any earlier draw conservatively invalidates this
  confidence because its effects on VRAM are not rasterized.
  Initial preframe colors alone are never classified as fresh;
- No original GP0 packet data, palette color values, textures,
  VRAM bytes or rendered pixels are emitted to its metadata report.

Hardware-specific constraints are deliberate: wrapped VRAM transfers,
overlapping copies, 2 MB VRAM bank modes, enabled bit15 mask writes,
GPU fill operations, lines and unknown primitives are **rejected
instead of silently simulated incorrectly**. A real complex game
trace is likely to include these and may require extending a
separately verified emulator model before the trace can be audited.

Even for supported packet types, this engine does **not** emulate
GPU rasterization, blending, texture cache, GPU clock ordering or
draw-time CLUT cache contents. Therefore it reports **conditional
memory state derived from a supplied trace**, not a proven palette
sample. The exporter **does not itself acquire a GP0 trace**.

## Strict private input format

UTF-8 JSONL, with exactly one header record:

```json
{"kind":"WA1_PRIVATE_GP0_CPU_UPLOAD_DRAW_TIMELINE","schema":1,"frame":1200,"capture_phase":"before_first_packet","initial_vram_sha256":"<64 lowercase hex bytes fingerprint>"}
```

Each subsequent JSON line is one whole GP0 packet, including all
A0 pixel data words. For example, this is a **synthetic** E6
mask-disabled packet for frame 1200:

```json
{"frame":1200,"words":[3858759680]}
```

For A0 uploads, the `words` array is:
`[A0_command, dest_xy, transfer_wh, all_32bit_pixel_data_words]`.
It may contain more than Stage428's fixed-size 32-word packet limit,
but must still be within Stage437's memory/trace caps.

Do not fabricate packet words from screenshots, post-frame VRAM
or CUE files; those cannot identify exact command chronology.
Prefer instrumentation capturing the original emulator's real GPU
port writes and a snapshot immediately before trace collection.
Label frame and scope privately; an internally consistent JSONL
is **not** proof that the trace is complete or unmodified.

## Owner-local run (when original trace becomes available)

```sh
python tools/audit_private_gp0_upload_timeline.py \
   /private/WildArms/CDSTG.BIN \
   /private/WildArms/gpu/initial_before_packets.u16le.bin \
   /private/WildArms/gpu/complete_ordered_packets.jsonl \
   --map-index 2 \
   > /private/WildArms/gpu/stage437-private-timeline-report.json
```

All inputs and the metadata report remain **outside public GitHub**.
The original files are not copied to Actions or shipped in a Switch
NRO. Only synthetic test fixtures can appear in public CI.

## What remains unproved

1. No initial-before-packet real VRAM and no genuine ordered GP0
   packet trace have yet been obtained from the original game.
   Stage429–432 snapshots were designed around a paused/post-frame
   witness, not a synchronized pre-trace capture.
2. The GPU's texture/CLUT cache and framebuffer writes are not modeled;
   even a fresh CLUT memory upload is not automatic evidence of
   the palette actually sampled by the GPU.
3. The candidate source row↔decoded atlas/VRAM upload/visible roof
   linkage and exact scene geometry remain unverified.
4. A still screenshot comparison from Stages433–434 is a separate
   visual gate, not a substitute for draw-time source attribution.
5. Replay acceptance is conditional on a trustworthy trace with
   complete packet boundaries and true timing. JSON headers alone
   cannot authenticate emulator provenance.

## CI acceptance

`tests/test_audit_private_gp0_upload_timeline.py` exercises
synthetic A0/80 uploads, draw order, one-halfword mutations, odd
pixel padding, non-overlap enforcement, E6 masking guards,
candidate row matches, invalid traces and privacy-only reports.
It does not contain a ROM, original VRAM or any copyrighted art.

Successful CI confirms the parser's **strict supported subset**,
not authenticity of Surf Village or PlayStation texture rendering.
