# Stage424 — original CDSTG palette-like rows and candidate offset tables

## Source-grounded measurements

This study examines the user's PRIVATE original Wild Arms (USA) PlayStation
`CDSTG.BIN`, not synthesized or downloaded game assets. The independent
ISC-licensed WA1Tools reference (`wa/map.py`) establishes the
`0x91000`-byte fixed map records and their graphics region at `0x15000`:
https://github.com/cebix/wa1tools

Stage422 indexed **127 ordinary map records** plus exceptional dummy map
**#25**. Stage423 verified **seven** next-pointer-bounded original WA1 LZSS
graphics streams in map #2 **Surf Village**, but neither a palette map nor
tile arrangement is proven.

The current private audit examines uncompressed candidate graphics regions
**#0 and #5** across all 127 ordinary original maps. It does not interpret
the exceptional dummy block.

| Observed property | Actual original-data measurement |
| --- | ---: |
| Ordinary maps whose first graphics region length is a multiple of 512 bytes | **127/127** |
| Ordinary maps whose region #5 length is a multiple of 32 bytes | **127/127** |
| Distinct full SHA-256 values of the first graphics region | **101** |
| First-region length in 512-byte banks | **3–13 banks** (not uniform) |

This is a strong structural indicator that graphics region #0 contains
fixed-width records, potentially banks of 16-bit PS1 color-like words.
**A 512-byte chunk is compatible with 256 BGR555 words or sixteen 16-color
candidate rows. Neither CLUT semantics nor pixel assignment is yet proven.**

## Representative map: Surf Village (#2)

| First graphics region measurement | Original-derived count |
| --- | ---: |
| Length | **3,584 bytes = 7 × 512** |
| Hypothetical 32-byte rows, 16 × u16 words per row | **112** |
| Bytewise-distinct 32-byte rows | **85** |
| All-zero rows | **12** |
| Rows with first u16 word zero | **86** |
| Rows containing at least one u16 with bit 15 set | **76** |
| Separate graphics region #5 | **2,304 bytes**, multiple of 32 |

These are raw-word statistics. Bit 15 is **not** validated as
transparency/STP without observing genuine PlayStation rendering; neither
zero colors nor zero rows alone establish actual tile transparency.

The final two graphics regions for map #2 both begin with four strictly
increasing, 4-byte-aligned region-relative numbers starting with zero.
This may represent an internal offset table, but **no script, tile ID,
world coordinates, sprite or tilemap interpretation follows from four
integer values**. The final record has no following pointer, so its size
to the end of the map record is just an upper bound.

A survey of the remaining 126 normal maps also finds varying similar
trailing prefix sequences. Such structural repetition motivates targeted
study but does not establish common semantics.

## Reproducible metadata-only analyzer

```sh
python tools/audit_cdstg_color_candidates.py \
  /private/WildArms/CDSTG.BIN \
  > /private/WildArms/stage424-color-candidates.private.json

python -m unittest discover -s tests \
  -p 'test_audit_cdstg_color_candidates.py'
```

The source file, extracted textures, 16-bit palette values, maps, original
game text and screenshots never enter GitHub or CI. Only counts, sizes,
hashes and unverified offset-run metadata are emitted. Public regression
tests construct artificial PS1-like pointer data and synthetic 16-word
rows; they include an intentionally dummy exceptional record and
negative cases for unsorted pointers and unconvincing offset prefixes.

The first-region length is not a mandatory validation gate for all possible
game releases: the analyzer reports unexpected lengths rather than
discarding a map. The only mandatory pointer checks are boundedness,
4-byte alignment, strictly increasing candidate locations and minimum
run length.

## Gates before restoring the actual Surf Village scene

1. Identify the actual PS1 code or GPU transfer that maps candidate
   palette rows to decoded sections #6–12 (validated 4×32KiB + 3×64KiB
   in Stage423).
2. Establish true pixel packing, swizzle, palette-row indices and the
   game's tile-placement layout. Do not infer dimensions solely from
   output length or same-index adjacency.
3. Validate a small private-only candidate rendering against a genuine
   PS1 framebuffer or an independently captured original screenshot,
   including color-zero/STP/alpha handling.
4. Import only the validated original pixels and positions into the
   Switch field scene via private owner-supplied resource files.

**This stage classifies probable color-table/offset-table regions.
It does not yet produce an authentic Surf Village scene image.**
