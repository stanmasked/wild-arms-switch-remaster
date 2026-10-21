# Stage428 — private PS1 GPU CLUT coordinate observations for Surf Village

## Goal

Stage426 produced 112 original-source palette-row preview candidates from
real Surf Village CDSTG data. Stage427 provided exact occurrence searches in
original raw PS1 VRAM. **A VRAM occurrence is not proof that the GPU used
the row.** Stage428 adds a second, independent input: complete **GP0 command
packets captured by the original PS1 emulator** at a documented frame.

This stage can establish a **conditional coordinate-linked observation**:
a decoded 4bpp textured draw packet references CLUT coordinate (x,y), and
the post-frame 1024x512 little-endian VRAM snapshot at (x,y) contains
exactly the 16 u16 palette words from a candidate CDSTG bank row.
Unlike Stage427's capped coordinate samples, Stage428 reads and checks
the exact raw current VRAM bytes at each referenced coordinate.

**Still unproved:** that those exact bytes were in VRAM when the command
actually sampled the CLUT, which underlying LZSS stream supplies the
texture, the texture's tile placement, alpha/STP behavior, or any visible
pixel equality with an authenticated PS1 screen.

## Inputs are OWNER-PRIVATE and never enter public CI

1. The owner's genuine Wild Arms USA `CDSTG.BIN` used in Stages422–427.
2. A full raw, non-image PS1 VRAM snapshot: **1,048,576 bytes**, organized
   as 1024 × 512 little-endian 16-bit words. The snapshot is intended
   to be captured **after executing the draw packets** for a single
   Surf Village frame, not as a PNG or emulator savestate.
3. A **trusted-emulator-generated** UTF-8 JSONL file containing the
   frame's **complete, already packetized** GP0 command writes, in order.
   Do not pass a raw DMA word stream with unknown packet boundaries.

Trace header (JSON object on first line):

```json
{"kind":"WA1_PRIVATE_PS1_GP0_PACKET_TRACE","schema":1,"vram_sha256":"<64 lowercase hex SHA-256 of captured raw VRAM>","frame":1200,"capture_phase":"post_packet_frame"}
```

Every following line is a single entire GP0 packet. The example below
shows a **synthetic**, not original-game, 4bpp textured triangle packet
with CLUT=(32,19), texture-page value zero:

```json
{"frame":1200,"words":[603979776,100,79829772,200,0,300,0]}
```

(Decimal words are required; `0x...` strings are deliberately rejected.
These illustrative words do not constitute an authenticated PS1 capture.)

Local invocation:

```sh
python tools/audit_surf_gp0_clut_references.py \
  /private/WildArms/CDSTG.BIN \
  /private/WildArms/surf_village_vram_1024x512_u16le.bin \
  /private/WildArms/surf_village_complete_gp0_packets.jsonl \
  --map-index 2 > /private/WildArms/stage428-gp0-observations.json

python -m unittest discover -s tests \
  -p 'test_audit_surf_gp0_clut_references.py'
```

Important: a JSONL header with a matching digest merely links *files*.
It does not authenticate that an emulator truly generated the packets,
that the capture covers all GPU events, or that its post-frame VRAM matches
the historical values used at every draw. Record emulator version, capture
method, original disc checksum, frame/frame-step method and scene position
separately in the private evidence log.

## Decode contract

- GP0(E1h) draw-mode establishes a texture-page depth for following
  textured *rectangles*. If the trace starts after E1 or contains an
  unsupported packet, rectangle page state is treated as unknown rather
  than guessed. A textured *polygon* carries its own page in the second
  UV word.
- Supports fixed-size and variable-size GP0 textured rectangle commands,
  textured flat/gouraud triangles and quads. Verifies packet word count.
- Finds the CLUT encoded in the first UV word: CLUT-X = bits0..5 ×16
  **halfwords**, CLUT-Y = bits6..14 in 0..511. Rejects nonzero reserved
  bit15, and skips non-4bpp pages. For polygon TPAGE information,
  4bpp/8bpp/15bpp depth comes from TPAGE bits7..8.
- Uses **byte-exact** comparison, including bit15 in all sixteen words,
  between source candidate row and the post-frame VRAM row.
- Does not conflate identical candidate rows found in different banks:
  all matching candidate bank/row indices are retained.
- Skips all-zero or low-information source palettes by default (fewer
  than three distinct nonzero entries). This can introduce false
  negatives for legitimate flat palettes, so no-match is not an absence
  proof.
- Reports only hashes, source bank/row indices, draw packet ordinal,
  depth-consistent CLUT coordinates, texture page base and first UV.
  Original palette words, VRAM bytes, original disk art and GP0 packet
  words are never copied to JSON outputs.
- Limits recorded per-event evidence, while preserving the full
  counted number of 4bpp coordinate references and successful byte
  matches.

Reference used for hardware bitfields: **PSX-SPX**:
https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/
https://psx-spx.consoledev.net/dev/ps1/gpu/render-polygon-commands/
https://psx-spx.consoledev.net/dev/ps1/gpu/render-rectangle-commands/

## Falsifiable acceptance gates

1. **Public code CI:** all synthetic packet layouts, trace-snapshot
   linkage, bounded-size checks, rejects and privacy tests pass on the
   exact Stage428 commit.
2. **Private real-capture evidence:** an independently captured complete
   Surf Village GP0 trace and VRAM dump share the same frame and SHA256.
3. **Temporal verification:** inspect emulator instrumentation to ensure
   the CLUT was not overwritten between its actual draw and the
   snapshot; re-capture near individual draw commands if needed.
4. **Texture source connection:** trace VRAM uploads and texture-page
   coordinates to a specific decoded LZSS stream and subregion, not
   merely a similarly-colored row.
5. **Visual reconstruction:** align one small patch (roof or well) with
   an original PS1 framebuffer at the same camera/scene state before
   calling any art canonical or importing it privately to Switch.

No actual GP0 trace from the original game has been supplied for
Stage428. This is a tested investigation instrument, not a restoration
of Surf Village or proof of a specific game's GPU command.
