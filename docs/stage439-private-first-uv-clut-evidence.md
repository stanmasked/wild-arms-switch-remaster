# Stage439 — private first-UV 4bpp texture + palette linkage

## Goal

Stage437 accepts privately instrumented, ordered GP0 packets plus
a *pre-packet* 1 MiB PS1 VRAM snapshot and replays a strict subset of
CPU→VRAM (A0) and non-overlapping VRAM→VRAM (80h) transfers. It
compares the 16-word CLUT row found before a textured draw to one of
Surf Village's CDSTG candidate palette rows. Stage438 can independently
check modeled memory against a distinct, synchronized *post-packet*
snapshot, but cannot rasterize polygon drawing.

Stage439 adds one narrower question: **where does the first declared UV
address of a textured GP0 command point in modeled 4bpp VRAM, and
which modeled CLUT halfword would that texture index select?**

This is **not** a complete polygon/rectangle rasterization, verified
visible pixel, hardware CLUT-cache trace, texture-atlas-to-tile
attribution, or reconstruction of a Surf Village roof or well.

## Hardware detail / fail-closed assumptions

According to PSX-SPX:

- For 4bpp pages, a 16-bit VRAM texture word contains four consecutive
  4-bit indices, with index `u % 4` occupying its low-to-high nibble.
  The texture word address is `texture_page_base_x_words + floor(u/4)`
  and `texture_page_base_y + v`.
- The selected palette entry is one 16-bit word at
  `CLUT base x_words + index` on the CLUT row.
- GP0(E2h) contains X/Y texture-window masks and offsets across bits
  **0–19**; bits 20–23 are reserved. Nonzero texture-window fields
  can remap U/V.

Hardware references:
https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/
https://psx-spx.consoledev.net/dev/ps1/gpu/render-polygon-commands/
https://psx-spx.consoledev.net/dev/ps1/gpu/render-rectangle-commands/

**Conservative contract:** a first-UV texture probe is performed
ONLY after an explicit GP0(E2) with all texture-window fields zero
has been observed in that trace. If E2 has not appeared, the initial
window state is unknown and no source texture address is sampled.
If E2 is nonzero, sampling is likewise disabled until an explicit
E2 zero is observed. Bad packet lengths or reserved E2 bits fail
closed rather than silently normalizing GPU behavior.

Other GPU state and transfer restrictions remain those of Stage437:
A0/80 replay requires an explicit E6 transfer-mask-disabled state,
all VRAM regions must be within the supported 1024×512-word bounds,
overlapping GPU copies and unsupported GP0 commands are rejected.

## New private evidence fields

The Stage437/438 `clut_draw_events` receive
`first_uv_texture_probe`, which is one of:

- `TEXTURE_WINDOW_STATE_NOT_OBSERVED`
- `NONZERO_TEXTURE_WINDOW_NOT_MODELED`
- `MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW`

In the last case the metadata includes:
- texture-word X/Y coordinates in 16-bit VRAM words;
- referenced CLUT-row X/Y;
- SHA-256 fingerprints of the modeled source texture halfword and
  selected CLUT halfword;
- separate flags for whether that texture halfword and that particular
  CLUT halfword were explicitly loaded since the preceding GPU draw;
- a flag indicating index zero **only**, without treating it as
  transparent or black;
- strict caveats that the UV might not correspond to any visible
  rasterized pixel and texture/CLUT caches are not modeled.

The 4-bit pixel index, 16-bit palette word and raw texture/VRAM
bytes are NOT copied into the JSON report. Fingerprints are short-input
hashes and may be reversible by enumeration; even metadata-only
reports are owner-private and MUST NOT be committed to GitHub.

Probe status counts are computed for ALL supported 4bpp draws even
when the private sample list reaches Stage437's bounded
`max_evidence` cap.

## Private use after real GPU instrumentation exists

Run the existing Stage437/438 command on *real* pre-packet and
post-packet private VRAM data with an independently captured,
complete, ordered GP0 JSONL stream:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/pretrace.u16le.bin \
  /private/WildArms/gpu/ordered-gp0-packets.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/posttrace.u16le.bin \
  > /private/WildArms/gpu/stage439-private-first-uv.json
```

The paths are illustrative; no such synchronized original-game
capture has yet been obtained in this work session. The
PCSX-Redux REST screenshot and paused VRAM API cannot, by itself,
provide an ordered complete GP0 trace or authenticate the frame.

A successful modeled first-UV probe indicates only a **conditional
index-to-memory-and-palette address chain** in the supplied input.
It does not identify which original decompressed 4bpp stream or
sprite/roof tile belongs at that address, prove a draw-time GPU cache
sample, or establish framebuffer color equality. Those remain
separate recovery gates before original-style HD art can be
called faithful or imported into the private Switch build.

## CI

`tests/test_audit_private_gp0_texture_first_uv.py` uses only ROM-free
synthetic 1 MiB buffers, artificial 16-color rows and GP0 packet words.
Tests cover E2 state, all four nibble offsets, texture page X/Y
addressing, CLUT entry selection, pre-/post-draw upload confidence,
sample caps, non-4bpp exclusion, invalid inputs and privacy.

**CI success proves only that this supported subset of the analytic
model passes synthetic regressions, not that Surf Village has been
restored or that original emulator GPU evidence has been acquired.**
