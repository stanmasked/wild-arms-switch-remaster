# Stage427 — original PS1 VRAM memory-occurrence evidence for Surf Village

## Why this stage follows the 112 real-source palette previews

Stage426 exposed seven genuine Surf Village CDSTG LZSS graphics streams and
112 candidate BGR555 palette rows (seven 512-byte banks × sixteen rows).
The previews are original-source *atlas diagnostics*, not verified colors
used by the PlayStation during gameplay. Ordinally pairing a bank and a
stream or preferring natural-looking wood colors is not proof of a CLUT.

This stage provides a **private-only exact byte matcher** for an independent
original PS1 VRAM capture. Its deliberately narrow question is:

> Does a candidate sequence of sixteen little-endian palette words appear
> on a 16-word-aligned grid within a genuine, full-size PS1 VRAM dump?

**Even a match means ONLY that a 32-byte sequence exists in memory.**
It does NOT establish a GPU CLUT selection, DMA upload source, texture page,
4bpp pixel layout, the relevant sprite/tile, or an on-screen map pixel.

## Evidence input contract — all data stay private

1. Use the owner's authentic PS1 Wild Arms (USA) disc to run Surf Village
   (field map #2) in a trusted PS1 emulator. Do not upload disc data to CI.
2. Privately capture PS1 **raw VRAM**, precisely 1024 × 512 16-bit words
   little-endian, left to right and top to bottom: **1,048,576 bytes**.
   The exporter does not accept PNG, RGB/RGBA screenshots, save states,
   interleaved GPU metadata or a cropped texture page.
3. Record capture provenance privately: emulator name/version, game disc
   revision, game location/scene, relevant frame or pause point, endian
   and VRAM output layout, and the complete snapshot hash. Capture timing
   matters because stale VRAM may contain unrelated palette data.
4. Keep the VRAM image, original CDSTG.BIN, owner screenshots, palette
   values and any derived art completely outside public GitHub,
   GitHub Actions artifacts and normal downloadable builds.

Example command (after producing a legitimate private VRAM snapshot):

```sh
python tools/audit_surf_vram_palette_occurrences.py \
  /private/WildArms/CDSTG.BIN \
  /private/WildArms/surf_village_ps1_vram_u16le.bin \
  --map-index 2 > /private/WildArms/stage427-vram-matches.json

python -m unittest discover -s tests \
  -p 'test_audit_surf_vram_palette_occurrences.py'
```

The source, VRAM and JSON output above are private evidence; public CI uses
**only synthetic CDSTG/VRAM fixtures** and has no original game material.

## Conservative matcher semantics

- Reuses Stage426 validation for real next-pointer-bounded WA1 LZSS streams
  and 512-byte candidate banks. Never mistakes a marker for a complete
  decoded stream.
- Decodes each bank as sixteen 32-byte *candidate* color rows. It does
  **not** pair any row with a texture or select a row by visual appearance.
- Compares the actual sixteen u16 words byte-for-byte, **including bit15**.
  This does not assign STP or transparent index semantics.
- Restricts potential 4bpp CLUT locations to VRAM **x in 0,16,...,1008
  (word coordinates)** and **y in 0,...,511**. No matches cross scanlines.
- Excludes all-zero rows and rows with fewer than three distinct nonzero
  color words by default. Such low-information rows produce broad false
  positives in uninitialized or flat regions. Exclusion is a heuristic:
  it can miss legitimate simple palettes.
- Groups identical candidate row bytes across multiple banks, preserving
  **all** bank/row references. A repeated row never becomes evidence that
  one particular bank was selected.
- Reports SHA-256 digests, candidate indices, matching coordinate counts,
  and up to sixteen sample locations per distinct row (configurable 1–64).
  It does not print the 32-byte sequence or the VRAM contents. A truncated
  sample list still reports the **full count**.

The allowed CLUT grid reflects one technical 4bpp hypothesis. Correct
capture format, location timing, memory endianness, GPU state and texture
depth need *independent verification*. A zero-match result is **not**
evidence that the source palette is unused.

## Falsifiable next gates

1. Obtain a private raw VRAM snapshot from a controlled Surf Village
   gameplay frame, then run this exact-match tool and retain its hash.
2. Repeat at several documented frames or camera positions to distinguish
   stable vs transient or unrelated occurrences; compare metadata only.
3. Independently inspect actual PS1 GPU drawing commands (including the
   CLUT coordinates in the polygon/sprite packet and texture-page info)
   and/or texture upload traces. Only those can link an occurrence to
   runtime use. A memory hit alone cannot.
4. Verify index packing, tile/sprite placement and STP behavior against
   the original framebuffer. Reconstruct a private reference-aligned
   micro-patch (for example the Surf Village well or one roof), not a
   guessed full scene.
5. Only then transfer validated map reconstruction data through a
   user-private asset path to the Switch renderer.

## Testing and privacy

`tests/test_audit_surf_vram_palette_occurrences.py` includes synthetic
checks for exact matches, repeated rows, absent matches, 16-word alignment,
scanline edges, strict bit15 matching, the memory size contract, false
positive exclusions, sample truncation, invalid parameters, corrupt CDSTG
and report schema privacy. No genuine PS1 artwork or firmware is required.

**Stage427 deliverable:** a tested method to gather **candidate original
memory occurrences**, not a verified CLUT assignment or a rendered Surf
Village. No original emulator VRAM capture has yet been supplied for
this stage.
