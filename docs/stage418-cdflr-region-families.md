# Stage418 — shared and variable CDFLR candidate region families

## Source and verification

All observations below are from the **actual privately extracted** `CDFLR.BIN`
in the user's original Wild Arms USA PS1 image, not a synthetic test fixture.
The original container has 67 fixed `0x3A000`-byte slots. Each contains 58
validated, increasing 32-bit KSEG0-address-like pointers, indexed 0–57.

### Important Stage417 correction

The 58 pointer words occupy exactly **232 bytes**. Between their end and the
first data pointer at `0x100` are **24 opaque bytes**. **Only slot #0 is
all zero; slots #1–66 contain nonzero data there.** The original synthetic
Stage417 code had wrongly required a zero terminator/padding in each slot.
That bug was independently discovered by re-running against the genuine file,
and was corrected in PR #96 before Stage418 was based on it. These opaque
bytes are not discarded or assigned a meaning.

## Cross-slot byte-equivalence study

Each of the 16 candidate sections at pointer indexes 42–57 was compared
across **all 67 slots** by size and SHA-256 of the exact bounded region.
A digest equality has also been cross-checked by direct byte comparison on
sampled slots. Counts of distinct content hashes:

| Pointer index | Hypothesized region | Unique bytewise contents / 67 |
| --- | --- | ---: |
| 42 | u16 color-like table, normally 512 bytes | 46 |
| 43 | linked variable-length region | 40 |
| 44 | u16 color-like table, normally 512 bytes | 47 |
| 45 | linked variable-length region | 41 |
| 46 | u16 color-like table (512 bytes) | **1** |
| 47 | linked region (11,392 bytes) | 18 |
| 48 | u16 color-like table (512 bytes) | **1** |
| 49 | linked region (9,188 bytes) | **1** |
| 50 | u16 color-like table (512 bytes) | **1** |
| 51 | linked region (10,544 bytes) | **1** |
| 52 | u16 color-like table (512 bytes) | **1** |
| 53 | linked region (12,116 bytes) | 18 |
| 54 | u16 color-like table (512 bytes) | **1** |
| 55 | linked region (10,932 bytes) | **1** |
| 56 | u16 color-like table (512 bytes) | **1** |
| 57 | final variable-length region (to slot end as maximum only) | 44 |

**Six** even-index color-like tables (#46, #48, #50, #52, #54, #56)
are byte-for-byte invariant among all 67 slots. **Three** paired regions
(#49, #51, #55) are byte-for-byte invariant. Two paired regions (#47 and
#53) have exactly **18** distinct versions despite their fixed spans.
The early pairs (#42–45) vary substantially between slots.

This supports a *candidate* shared-resource versus variable-resource
partition, but does **not** prove that the shared groups are UI,
character sprites, music, or any other specific gameplay feature.

### Color-like data and the two exceptions

The standard 512-byte sections consist of 256 little-endian u16 words.
The invariant sections have these counts of words with bit 15 set:

| Pointer index | Set-bit-15 words / 256 |
| --- | ---: |
| 46 | 226 |
| 48 | 240 |
| 50 | 240 |
| 52 | 225 |
| 54 | 201 |
| 56 | 234 |

This is compatible with PlayStation 16-bit color-table conventions, where
bit 15 can carry special meaning. However neither the pixel index format nor
STP/transparency handling nor actual CLUT use has been confirmed.

Slots **#4 and #28** contain **224-byte** and **64-byte** color-like regions
at indexes 42 and 44, respectively — **112** and **32** u16 words instead
of 256. They retain the other six 512-byte candidates. Their corresponding
paired data regions are not invalid merely because the color-like span is
shorter. They must be preserved for a future decoder.

The last pointer #57 has no next pointer. Its reported span until the end of
the fixed slot is an *upper bound only*, not a proven encoded-data length.

## Private reproducibility

```sh
python tools/audit_cdflr_region_families.py /private/CDFLR.BIN \
  > /private/stage418-cdflr-families.json
python -m unittest discover -s tests -p test_audit_cdflr_region_families.py
```

The tool validates geometry and all 58 pointer words and reports only
hashes, counts, exception indices and size ranges. It deliberately does not
require the 24 opaque bytes to be zero. There are no raw palettes, pixel
streams, decoded art or original file bytes in stdout or the public repo.
CI uses only fake synthetic slots.

## Next evidence gates

1. Confirm the layout of candidate color tables and bounded paired-data
   structures against actual PlayStation display output, including #4 and #28.
2. Investigate invariant palette with variable data pairs (#46/#47 and
   #52/#53), which are excellent targeted cases for distinguishing shared
   color tables from variable indexed pixel data.
3. Find the expected dimensions/stride and compression grammar **without
   inventing a pixel layout from byte statistics alone**.
4. Establish actual slot-to-location selection using verified PS1 loader
   runtime evidence. Only then name a block as an original game map.

The original PS1 BIN, extracted resources, real RAM dumps and decoded
copyrighted assets stay off public GitHub.
