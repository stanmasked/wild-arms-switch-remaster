# Stage423 — evidence-gated Surf Village texture layout hypotheses

## Real original data studied

The original private user-owned PS1 USA `CDSTG.BIN` contains 128
`0x91000`-byte map blocks. The original map-name table identifies
block **#2 as Surf Village**. Its graphics area begins at map offset
`0x15000`, with a **15-entry strictly increasing** candidate graphics
pointer run. The first graphics pointer is at graphics-relative `0x100`.
This gives 14 next-pointer-bounded source regions plus an unbounded final
section, which must not be treated as one decoded texture automatically.

The independent, ISC-licensed WA1Tools project confirms the PS1 map
container and Wild Arms LZSS format:
https://github.com/cebix/wa1tools (`wa/map.py`, `wa/lzss.py`, `mapinfo`).

Seven bounded Surf Village regions decode with the **validated WA1 LZSS**
codec (exact expected uncompressed size, exact encoded endpoint with
only 1–3 alignment bytes remaining):

| Graphics region index | Decoded bytes | Compressed bytes incl. padding | Encoded bytes consumed | Byte entropy (bits/byte) | Fraction of zero 4-bit nibbles |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 32,768 | 14,612 | 14,610 | 5.060 | 23.85% |
| 7 | 32,768 | 18,252 | 18,251 | 5.853 | 12.89% |
| 8 | 32,768 | 12,924 | 12,921 | 4.525 | 38.89% |
| 9 | 65,536 | 17,400 | 17,398 | 5.230 | 26.16% |
| 10 | 65,536 | 20,520 | 20,517 | 2.955 | 70.13% |
| 11 | 65,536 | 17,448 | 17,446 | 2.167 | 78.89% |
| 12 | 32,768 | 11,312 | 11,309 | 3.472 | 64.89% |

All seven output buffers contain all possible 16 nibble values. This
property is **compatible with** indexed 4-bit textures, but does not prove
pixel encoding or image dimensions. Low-entropy buffers may include
blank space, masks, tiled layers, repeated data or another format.

## Avoid false reconstruction of the village

A 32,768-byte output could represent 256x256 **4bpp pixels** (as the
already verified battle icons do), or 128x256 **8bpp** pixels, or other
valid width/height arrangements. Similarly 65,536 output bytes could
represent 512x256 4bpp, 256x256 8bpp, or other layouts. Therefore **one
successful decompression is not equivalent to a validated image**.

The new tool `tools/audit_surf_texture_hypotheses.py` evaluates
candidate 4bpp low-nibble-first and 8bpp interpretations and practical
row widths of 128, 256, 512 and 1024 pixels, retaining only dimensions
within 64–1024 rows. Each candidate reports:
- source-derived `decoded_sha256`, compressed extent and unconsumed
  alignment bytes, with **no original byte content**;
- distinct byte counts, Shannon entropy, and frequency of zero nibble
  values;
- horizontal/vertical same-index adjacency under an explicitly
  hypothetical row-major layout;
- independent-frequency expected coincidence as a baseline.

Adjacency differences can **help prioritize** width/packing
hypotheses. They cannot prove that the decoded buffer is a contiguous
image, that a specific tile is on-screen, or that a particular 16-color
palette should be applied. No palettes are guessed or included.

### Reproduce privately, not in public GitHub/CI

```sh
python tools/audit_surf_texture_hypotheses.py \
  /private/WildArms/CDSTG.BIN --map-index 2 \
  > /private/WildArms/stage423-surf-geometry.private.json

python -m unittest discover -s tests \
  -p 'test_audit_surf_texture_hypotheses.py'
```

The tests use synthetic all-zero WA1 LZSS streams and artificial
`CDSTG.BIN`-like containers, including a disabled dummy map and
negative geometry/source-length cases. Actual original graphics,
palettes, pixel buffers, map scripts and privately generated metadata
remain out of GitHub.

## Independent visual reference

The Video Game Atlas hosts a **Surf Village** player-screen-captured
map stitched by VGCartography (1420x1260):
https://www.vgmaps.com/Atlas/PSX/ .

The atlas/map is a useful future *visual comparison reference*,
but is not a proof of the original GPU layer order or the internal PS1
asset format. Do not copy its copyrighted pixel art into public code,
CI fixtures or distributed assets. Source-grounded rendering should
ultimately be compared with a trusted reference-PS1 framebuffer.

## Next necessary gates for a first faithful Switch field scene

1. Trace non-compressed map-graphics regions #0–5 and #13–14 to actual
   tile arrangement, actor graphics and 16-bit CLUT structures.
2. Identify the consumer routine or emulator VRAM transfer that maps
   decoded regions #6–12 into image tiles; verify 4/8bpp, swizzle,
   width/height, palette selection and transparency.
3. Render a **private-only** small, reference-aligned Surf Village
   patch with exact original colors and tile positions.
4. Compare side-by-side against genuine PlayStation gameplay and only
   then expose the verified patch through the Switch field engine.

Current milestone is **seven genuine streams decoded and profiled**,
not a complete reconstructed map or an emulator screenshot.
