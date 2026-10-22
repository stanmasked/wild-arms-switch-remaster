# Stage440 — private decoded Surf Village stream → VRAM byte-run occurrences

## Objective

Stages426–439 established a series of **instruments** for private
original-source extraction, candidate palettes, GP0 transfer replay
and conditional first-UV texture/CLUT addressing. They have NOT yet
identified a source texture sheet as the visible roof/well in a
genuine running Surf Village scene.

Stage440 adds the next independent falsifiable comparison:

**Does a sufficiently long consecutive sequence of bytes from one of
the original CDSTG WA1-LZSS-decoded graphics streams also appear
unchanged in a single scanline of a privately captured 1024×512×16
PS1 VRAM snapshot?**

A byte run is only an occurrence. Matching bytes do NOT identify
the GP0 upload responsible, the original game's current map,
4bpp swizzling, palette row, tile coordinates, a visible pixel,
a texture cache sample or the correct Switch rendering.

## Strict search geometry

`tools/audit_private_surf_stream_vram_runs.py` uses
`read_private_candidates()` from the established bounded stream
decoder. Decoded streams must be bytes objects between 64 and 65,536
bytes, divisible by 64. Source windows begin at 64-byte offsets.

It scans each of 512 private VRAM rows (2,048 bytes per row) at
32-byte increments, corresponding to X aligned to 16 GPU halfwords.
A candidate run begins with a high-information **64-byte** source
window and must contain at least **3 consecutive 64-byte blocks**
(192 consecutive bytes) that match in the same order on the same
VRAM scanline. The minimum is configurable from 2 to 32 for
diagnostics; default 3 reduces one-block false positives.

To avoid trivial coincidences, an eligible 64-byte anchor must have
at least 12 distinct byte values and 32 nonzero bytes. Repetitive
anchors found more than 16 times in the candidate source streams
are excluded instead of asserting ambiguous placement.

A matching run may extend across adjacent 64-byte candidate blocks
on the source side, but **never beyond a single 2,048-byte VRAM
scanline**. Matches starting at source offsets inside a larger
qualifying run are suppressed so a single run is not counted
multiple times. Blank or excessively repetitive preceding blocks
are not allowed to erase a qualifying subsequent run.

These conservative rules can create false negatives for authentic
textures that were tiled, rearranged, DMA-interleaved, shifted by
an odd alignment, copied across rows or transformed before upload.
**No result is NOT evidence that a source stream was absent from VRAM.**

## Output (owner-private metadata only)

The output JSON includes:

- exact VRAM snapshot SHA-256;
- number of source graphics streams and 64-byte source blocks;
- low-information/frequent anchor exclusions, searched VRAM
  positions, anchor hit count and total qualifying run count;
- at most 32 samples by default (configurable up to 256) reporting
  source stream ordinal/graphics region, source byte offset,
  VRAM X halfword/Y row, matching block count, and SHA-256 of
  the matched span and decoded source stream;
- explicit flags that original map identity, texture page, visible
  geometry and GPU command chronology remain unverified.

No raw palette words, pixels, decompressed original source bytes,
raw VRAM or GPU packet words are included in the JSON output.
The **hashes, coordinates and entire report remain private**;
these data can reveal aspects of copyrighted original resources
and must not be committed to public GitHub/Actions or NRO builds.

## Owner-local use

Once the owner's genuine `CDSTG.BIN` has been extracted from the
original PS1 CUE/BIN with Stage435/436 and a real VRAM capture has
been obtained with Stage429/430/432:

```sh
python tools/audit_private_surf_stream_vram_runs.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/surf_scene.u16le.bin \
  --map-index 2 --minimum-contiguous-blocks 3 \
  > /private/WildArms/gpu/stage440-private-byte-runs.json
```

The paths are examples, not actual downloaded files. The user's full
Wild Arms BIN is larger than the connected Drive download limit and
has not been fetched or analyzed as a whole in this environment.

## Relationship to next evidence stages

A long byte run can narrow a **candidate source-to-memory mapping**.
To identify a canonical Surf Village texture:

1. Independently verify original game/map, camera and source revision;
2. Instrument an authentic emulator trace of the GP0 uploads and
   texture-page operations, including packet boundaries and timing;
3. Match a relevant texture page region and first-UV address from
   Stage439 to an observed source-memory run, not just a palette;
4. Independently validate GP0 4bpp CLUT, texture window, drawing
   geometry, bit15/STP and GPU texture-cache behavior;
5. Compare the actual visible roof/well pixels against genuine
   PCSX-Redux screenshots using Stages432–434.

No complete original GP0 trace or authentic Surf Village screenshot
has been captured by this PR.

## Synthetic CI contract

`tests/test_audit_private_surf_stream_vram_runs.py` contains 17
ROM-free tests using invented high-entropy 64-byte blocks. The
tests cover exact multi-block runs, source offsets, scanline
boundaries, 16-halfword grid alignment, low-information and repeated
anchors, distinct stream identities, false positives, input geometry,
sample limits and metadata-only privacy.

Passing these tests demonstrates a deterministic private matching
algorithm, not restored commercial game art.
