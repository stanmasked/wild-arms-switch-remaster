# Stage422 — real original field-map indexing: Surf Village candidate

## Reference format and corrections to previous assumptions

The independent, ISC-licensed [WA1Tools project](https://github.com/cebix/wa1tools)
(`mapinfo`, `wa/map.py`) identifies the **actual field-map source**
as `BIN/CDSTG.BIN`, rather than `CDFLR.BIN` which contained the
verified battle icon sheets from Stage420.

WA1Tools establishes:
- **128 fixed `0x91000`-byte map blocks** in original `CDSTG.BIN`;
- map record **#25** is deliberately disabled/dummied-out;
- a **map-script/section pointer table of 18 little-endian u32 values**
  starting at map-relative byte offset `0x40`, based at `0x8014F000`;
- the separate map-graphics area begins at relative **`0x15000`**
  (candidate graphics RAM base `0x80164000`);
- the game name table lives in original USA `WILDARMS.EXE` at file
  offset `0x7578`, with pointer relocation:
  `file_name_offset = name_pointer - 0x80011420 + 0x800`.

This attribution is important: finding a valid original battle icon
does **not** mean the game field map has been rendered, and 18
nonzero/zero script pointers must **not** be confused with the PS-X-EXE
header's unrelated entry-PC fields.

## Measured observations on the user-owned original

A new local audit of the original 76,021,760-byte `CDSTG.BIN`
verified precisely **128 × 593,920** bytes, no remainder, and
**127 / 127** ordinary map blocks with:
- bounded map-script section pointers in the `0x00000..0x14FFF`
  record prefix; optional entries may legitimately be null;
- structurally ordered global script-entry and first script pointers;
- a separate candidate **graphics pointer run starting at graphics-relative
  offset `0x100`** and consisting of **10 to 31 increasing,
  word-aligned RAM addresses**;
- a distinct SHA-256 of each ordinary map's
  `[0x15000:0x91000]` graphics area.

Map #25 is retained separately as an **exceptional unclassified record**,
not rejected as corruption or silently omitted.

The *candidate* graphics list is the contiguous ascending RAM-looking
prefix at the start of the graphic area. Its length varies; a following
non-pointer word is **not automatically a zero terminator** or evidence
of a confirmed graphics codec. The graphics area is not decoded, and its
final item’s actual length is not proven from the slot boundary.

### Representative original maps

| Map ID | Name resolved privately from USA original EXE | Candidate graphics pointers | Global script entries |
| ---: | --- | ---: | ---: |
| 0 | Filgaia | 31 | 121 |
| 1 | Elw World | 15 | 7 |
| **2** | **Surf Village** | **15** | **73** |
| 3 | Curan Abbey | 24 | 180 |
| 4 | Adlehyde | 22 | 162 |
| 5 | Adlehyde | 19 | 82 |
| 6 | Adlehyde Castle | 21 | 138 |

These names are short referential identifiers from the privately
supplied original USA executable, not claims that a map number matches
the player's progression order. Separate map IDs can share a name.

Candidate graphics pointer counts are distributed across **18**
distinct sizes (10 through 26, plus 31). The specific sizes/relationships
must be preserved rather than forcing every original map into an
identical layout.

## Stage422 public tool and synthetic tests

```sh
python tools/audit_cdstg_maps.py /private/WildArms/CDSTG.BIN \
  > /private/WildArms/stage422-map-catalog.private.json

# Optional: include original map names in a PRIVATE local report only.
python tools/audit_cdstg_maps.py /private/WildArms/CDSTG.BIN \
  --executable /private/WildArms/WILDARMS.EXE --include-names \
  > /private/WildArms/stage422-map-names.private.json

python -m unittest discover -s tests -p test_audit_cdstg_maps.py
```

The default audit has **no copyrighted original strings in stdout**,
only map IDs, bounds, hashes, pointer counts and explicit interpretation
limits. An opt-in `--include-names` mode reads the *private* executable
and emits literal original names into a **private local report**; the
interpretation/encoding of non-ASCII names needs the upstream game's
text decoder. None of these reports should be uploaded to public GitHub.

The public tests use **synthetic fake CDSTG blocks**, a dummy exceptional
record, synthetic script pointers and a tiny synthetic PS-X-EXE name
table. No PlayStation ROM, executable, art, dialogue, save or music is
contained in the repository or CI.

## Why Surf Village is the first practical target

Map #2 is **Surf Village** (from the actual original map name table).
It has 15 leading candidate graphics pointers, 73 global script entries,
and a known fixed `0x7C000`-byte maximum graphics-area extent.

These are strong entry points for a decoder investigation, but the
current output is **structural indexing only**; it is not the original
village image. Before asserting a faithful recreated village:
1. Identify and independently validate the graphic-section format,
   compression, palettes, 2D layers and geometry inside CDSTG map #2.
2. Resolve item boundaries, especially the final variable-length
   graphics section, without consuming unrelated padding.
3. Compare any private local rendering against a *real* original PS1
   reference frame. The existing fake-prototype map is **not** such a
   reference.
4. Only then implement a **private owner-supplied import pipeline**
   into the existing Nintendo Switch field renderer.

The Stage421 opt-in original battle-icons preview remains independent.
It does not load or display CDSTG map #2.

The private original `CDSTG.BIN`, `WILDARMS.EXE`, potential decoded
assets and local metadata remain **outside public version control**.
