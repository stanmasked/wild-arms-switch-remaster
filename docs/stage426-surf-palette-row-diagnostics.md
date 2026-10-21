# Stage426 — real Surf Village source pixels with color-row comparison

## Status and purpose

The privately extracted **Wild Arms (USA) CDSTG.BIN** includes map #2,
**Surf Village**. Previous stages independently verified:
- exactly **7 candidate 512-byte banks** in map graphics region #0;
- exactly **7 next-pointer-bounded Wild Arms LZSS streams** (#6..12), four
  yielding 32KiB and three yielding 64KiB;
- index data, when provisionally unpacked as low-nibble-first 4bpp,
  visibly forms recognizable roofs, woodwork, a well, small environment
  assets, character/animal frames, etc.

The remaining key question is **which of each bank's 16 candidate color rows,
if any, was actually used for an individual texture or tile in PS1 VRAM?**

This stage does *not* auto-select a winner. It supports falsifiable private
comparisons of all candidate rows without publishing copyrighted game art.

## Authentic original-source observations

For original Surf Village, 7 × 512-byte candidate banks each contain
16 × 32-byte rows, each 16 × little-endian u16 words. This provides
**112 candidate 16-color rows**, of which **85** are byte-distinct and
**12** contain only zero u16 values.

The seven verified source streams include all sixteen possible 4-bit
indices under the 4bpp low-nibble-first hypothesis. For the output sizes:
- 4 × 32768 bytes allow a hypothetical 256 × 256 4bpp image;
- 3 × 65536 bytes allow a hypothetical 512 × 256 4bpp image.

The ordinal pairing hypothesis is **stream #6 -> bank #0, #7 -> #1,
... #12 -> #6**. This is one plausible relationship because the counts
match, but there is still no independent VRAM-upload or emulator-trace
proof of this order. A selected CLUT row is **not** necessarily applied
to an entire sheet: PS1 sprites/tile pages may select different palette
rows within a single source atlas.

The private diagnostic experiment renders **all 16 rows for each
ordinally paired stream**, **112 image variants** in total, and separately
renders a seven-stream overview with row 0. Original pixels and colors
are read from the user's private game container; they are not invented
illustrations. Some choices produce plausibly brown/golden wooden houses
and building roofs, while others shift them or character/animal sprites
to artificial vivid hues. Visual plausibility alone is **not** original
palette confirmation, especially for color cycling, special effects and
STP/alpha.

### PS1 technical distinction

The provisional channel decoding is PS1 15-bit color:
- Red: bits 0..4;
- Green: bits 5..9;
- Blue: bits 10..14;
- Bit 15: **ignored in this diagnostic**; its runtime special
  transparency/blending role has NOT been confirmed for this material.

Color word zero is treated as RGB(0,0,0) only for inspection. This is
not a claim about transparent pixels in PlayStation rendering.

**Image aspect ratios are preserved** by the new opt-in exporter:
a 512x256 candidate is scaled into its bounding box as a 2:1 image,
never stretched into a square. The original decoded buffers themselves
are not rescaled or modified.

## What the public code does

- \`tools/audit_surf_palette_rows.py\`: validate the actual private
  CDSTG map structure; inspect precisely bounded WA1 LZSS outputs;
  count/CRC-free SHA-256 fingerprint candidate palette rows; report
  row uniqueness, zero/high-bit counts and hypothetical nibble-index
  occupancy **without emitting raw source bytes or any palette values**.
- \`tools/export_surf_palette_candidates.py\`: **separate, manual,
  private-only** Pillow PNG exporter of all 16 candidate rows per stream,
  with aspect-preserving nearest-neighbor previews. Refuses to overwrite
  existing private outputs and labels each file **UNVERIFIED**.
- \`tests/test_audit_surf_palette_rows.py\`: ten **synthetic-only**
  regressions covering 32/64KiB true WA1 stream bounds, 16-row handling,
  BGR555 channel masks, nibble order, count mismatches, absent or partial
  streams, 512-byte bank geometry, dummy maps, privacy and aspect ratio.

### Private original reproduction

\`\`\`sh
# All raw assets and metadata stay on a private working disk.
python tools/audit_surf_palette_rows.py \
  /private/WildArms/CDSTG.BIN --map-index 2 \
  > /private/WildArms/stage426-candidate-rows.json

python -m pip install Pillow
mkdir -p /private/WildArms/stage426-preview
python tools/export_surf_palette_candidates.py \
  /private/WildArms/CDSTG.BIN \
  /private/WildArms/stage426-preview --map-index 2

python -m unittest discover -s tests \
  -p 'test_audit_surf_palette_rows.py'
\`\`\`

Never commit original game disc/EXE, CDSTG, screenshot, decoded
palettes/indices, derived PNGs or owner-private diagnostics into
GitHub, GitHub Actions artifacts, or public release builds.

## Acceptance gates before claiming a faithful Surf Village

1. **Link an actual CLUT row to an actual decoded texture subregion** by
   original PS1 code/VRAM upload trace; the count equality is
   insufficient, and multiple rows may be used within one atlas.
2. Verify pixel packing and transparency/STP and original VRAM page
   dimensions, not just byte counts or human-recognizable texture art.
3. Recover tile/geometry position and layer order of at least a small
   landmark: roof, wall, well or ground patch in Surf Village.
4. Reconstruct **only privately** a reference-aligned patch and compare
   to a genuine original PlayStation captured frame under controlled
   scene/camera conditions.
5. Import a validated patch through a private-owner asset path into
   the Switch field renderer, without distributing original art.

**Milestone reached:** 112 genuine-source, colorized *diagnostic texture
candidates* and a reproducible source-to-color-row inspection pipeline.

**Not reached:** verified per-pixel CLUT selection, a complete Surf Village
scene, or a run of that scene on the Nintendo Switch emulator.

## Independently documented original format

Christian Bauer's ISC-licensed WA1Tools
https://github.com/cebix/wa1tools (\`wa/map.py\`, \`wa/lzss.py\`,
\`mapinfo\`), already used in Stages420–425.
