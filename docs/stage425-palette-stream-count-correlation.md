# Stage425 — correspondence of color-like 512-byte banks and verified map graphics

## Original source basis

This stage cross-correlates two **independently established observations**
from the owner's private PS1 Wild Arms (USA) `CDSTG.BIN`:

1. Stage424: the first graphics region of **all 127 non-dummy map
   records** is a whole multiple of **512 bytes**. A bank could contain
   16 × 16 little-endian 16-bit color-like words, but is **not yet
   proven to be a PS1 CLUT**.
2. Stage422: the genuine Wild Arms 1 LZSS decoder (using Christian
   Bauer's independent ISC-licensed WA1Tools format reference,
   https://github.com/cebix/wa1tools) successfully decompresses
   **1,059 next-pointer-bounded map graphics regions** and validates
   their 0–3 remaining alignment bytes. Coincidentally matching
   output-length headers that fail strict decoding are excluded.

The new read-only `tools/audit_cdstg_palette_stream_correspondence.py`
uses Stage422's *validated stream counts*, not simple magic-word
counting, and compares them to `first_graphics_region_size / 512`.
The per-map report includes the verified candidate graphics-region
indices, full-region SHA-256, mismatch deltas and explicit uncertainty
flags. Original pixels, raw color values and scripts are not emitted.

## Results from actual original image

| Comparison | Original maps |
| --- | ---: |
| Ordinary maps scanned | **127** |
| Exact 512-byte bank count = valid LZSS stream count | **122** |
| Extra candidate bank(s), compared with validated streams | **5** |
| More validated streams than bank count | **0** |
| Non-512-byte-aligned first graphics region | **0** |
| Intentionally excluded dummy map | **#25** |

**122 / 127 = 96.1% exact count agreement**, a substantial
additional structural correlation. It makes a relationship between
initial color-like banks and downstream compressed graphics more
plausible, but a numerical match does **not** prove the mapping of
bank *k* to texture/stream *k*, PS1 CLUT interpretation, actual palette
selection, alpha/STP or game coordinates.

### Preserve the five real exceptions

| Map ID | Original map name (private USA EXE) | 512-byte candidate banks | Strictly verified LZSS regions | Extra banks |
| ---: | --- | ---: | ---: | ---: |
| 0 | Filgaia | 11 | 7 | 4 |
| 27 | Adlehyde | 10 | 9 | 1 |
| 29 | Adlehyde | 10 | 9 | 1 |
| 97 | Unnamed in source table | 11 | 6 | 5 |
| 117 | Adlehyde | 10 | 9 | 1 |

None should be treated as corrupt; extra candidate banks may refer to
graphics outside the strictly bounded confirmed streams, extra color
banks for different actors/effects, or unrelated data. The final
graphics region has no next-pointer endpoint and is deliberately not
counted as verified compressed graphics.

### First target: Surf Village, map #2

- Initial graphics section = **3,584 bytes = seven 512-byte banks**.
- Seven independently verified graphics LZSS streams, with next-pointer
  region indexes **6, 7, 8, 9, 10, 11, 12**.
- Four streams yield 32 KiB each; three yield 64 KiB each.
- All seven compressed streams end at their respective bounded input
  endpoints with 1–3 bytes of padding.
- The one-to-one **count** matches, but there is still **no verified
  bank/row selection** for any of the seven streams, and not even
  proof that their pixel layout is standard row-major 4bpp.

## Reproduction — user-owned local data only

```sh
python tools/audit_cdstg_palette_stream_correspondence.py \
  /private/WildArms/CDSTG.BIN \
  > /private/WildArms/stage425-bank-stream.private.json

python -m unittest discover -s tests \
  -p test_audit_cdstg_palette_stream_correspondence.py
```

This command invokes the already validated `audit_cdstg_map_lzss`
routine. Tests use **artificial 32/64KiB LZSS streams and synthetic
fixed CDSTG-like blocks**, including dummy map, extra color-like
banks, incorrect pointer and stream truncation. No original game bytes
or derived images go into the repository, public CI or build artifacts.

## Next decisive proof gate

Trace map #2 texture/CLUT upload at a trusted reference PlayStation
execution checkpoint, or independently find the actual PS1 GPU
transfer consumer in the original game code. The evidence needed is
a binding between a specific decoded stream, an identified 16-word
color row and GPU destination/texture page coordinates.

A separate **private-only index-map contact sheet** can assist visual
diagnostics of possible packing, but is not allowed to be called an
authentic game scene without matching both palette assignment and
spatial composition against a real original framebuffer.

The Stage421 optional Switch battle icon preview remains separate:
correctly decoding battle icons does not recover a field background.
