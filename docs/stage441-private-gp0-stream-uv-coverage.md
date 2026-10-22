# Stage441 — source bytes that cover a modeled GP0 first-UV texture word

## Problem and acceptance scope

Stage440 scans an entire PRIVATE PS1 VRAM snapshot for at least three
consecutive 64-byte source-stream blocks, with source bytes obtained
only after the bounded Wild Arms LZSS decoder has accepted the game
owner's private CDSTG graphics streams.

Stage439 links a modeled first declared 4bpp UV coordinate to a VRAM
texture halfword and a selected CLUT halfword, conditional on a
complete ordered GP0 trace with explicit texture-window state.

**Stage441 combines both analyses at one specific modeled pre-draw
moment**. A matching source run must contain the first declared UV
texture halfword in the very same memory state that Stage437/439
reached after replaying all prior supported GP0(A0)/80 transfers.
Matching a source stream anywhere else in a post-frame VRAM dump no
longer qualifies for this narrower conditional link.

This establishes **conditional source-run coverage only**.
It does NOT establish an original GPU texture upload, the historical
sampled palette, triangle rasterization, visibility of the first UV,
texture-cache correctness, camera alignment, or the final identity
of a Surf Village roof/well texture.

## Implementation

- `tools/audit_private_surf_gp0_stream_uv_link.py` validates
  the owner's bounded WA1-LZSS decoded streams, indexes qualifying
  64-byte source blocks, excludes anchors with low diversity or
  more than 16 source occurrences, and compares only 16-u16-grid
  VRAM positions on the first UV's own scanline.
- A match requires at least **three consecutive 64-byte blocks**
  from one source stream in identical order, staying inside that
  VRAM scanline, whose inclusive region covers the queried *entire*
  16-bit texture word. Source offset and byte-span counts are
  recorded; source bytes and individual indices are not.
- When the Stage437 per-halfword upload chronology is available,
  the report separately states whether *every halfword of the
  matching run* was explicitly refreshed by supported uploads
  since the preceding draw command. Baseline-only or previously
  uploaded matching source data remains conditional/uncertain.
- `tools/audit_private_gp0_upload_timeline.py` builds the source
  index once from its privately verified `verified_streams`,
  attempts linkage at every 4bpp modeled draw where the Stage439
  first-UV probe is available, and retains complete counters
  even if the per-draw evidence sample cap is reached.
- If GP0(E2) texture-window state is unknown/nonzero, the first
  UV address is **not** inferred, the source run is **not**
  sampled and the report explicitly says why.
- Stage438 optional post-packet VRAM reconciliation retains its
  separate all-known / known-after-draw proof bounds.

Both original owner files and the report stay entirely PRIVATE.
No ROM, CDSTG, game graphics, raw VRAM or GP0 trace enters GitHub CI.

## Private usage

For an authentic Surf Village investigation, the owner must first
locally extract `CDSTG.BIN` from their original game disc (Stages435–436),
capture a trustworthy **initial** raw VRAM, obtain a **complete ordered
and correctly packetized** GP0 trace that starts after that initial
snapshot, and optionally obtain final raw VRAM from precisely the same
interval. Stage432 paused snapshots alone are not such a trace.

Then use the existing entrypoint:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/initial.u16le.bin \
  /private/WildArms/gpu/complete-gp0-packets.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/final.u16le.bin \
  > /private/WildArms/gpu/stage441-private-source-uv.json
```

Each modeled textured event may contain
`first_uv_source_run_linkage` with:
`covering_byte_identical_run_count`,
`covering_runs_fully_refreshed_since_last_draw`,
`graphics_region_index`, source offset,
VRAM row/word coordinates, matching span length and run SHA-256.

These values are **diagnostic metadata, not verified game-art
placement**. Hashes of short graphics spans can be sensitive too;
do not publish the JSON.

## Limitations and next scientific proof gate

- Only exact, linear, one-row byte copies are considered. PS1
  texture pages may use rearrangements, interleaving, tiled DMA,
  non-grid alignment, texture-window transforms and other upload
  mechanisms not modeled here. Absence of a match proves nothing.
- The first declared UV word is not necessarily a pixel ever
  sampled by GPU rasterization. A polygon may be clipped, or its
  vertices may be off-screen.
- Even a freshly copied 192-byte run does not establish the
  original clip location, sprite boundaries, alpha/STP, bit15,
  display mode or PS1 texture/CLUT caches.
- Two identical source streams can yield multiple ambiguous
  hits; they remain separate references, not a unique source.
- Source CDSTG geometry and a complete authentic emulator GP0
  trace are still independent prerequisites, not outputs of this tool.

The next step toward a visually faithful original-style HD Surf
Village roof or well is to correlate a real original-game emulator
render, confirmed GPU upload chronology, visible polygon geometry
and source textures with a screen-space reference patch from
Stages432–434.

## Synthetic CI

`tests/test_audit_private_surf_gp0_stream_uv_link.py` provides
23 entirely artificial tests for source-run coverage at an exact
UV word, late/early transfers, stale memory after drawing,
same-row and grid boundaries, short/corrupt or repeated anchors,
multiple matching streams, GP0 E2 uncertainty, event caps,
conditional Stage438 reconciliation and metadata privacy.

CI passing only validates these conditional algorithms on synthetic
buffers. It is not an original Wild Arms artwork or GPU-capture
restoration certificate.
