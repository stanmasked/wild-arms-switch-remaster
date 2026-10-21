# Stage420 — reference-verified Wild Arms 1 graphics decompression

## Breakthrough: external format reference instead of codec guessing

Found Christian Bauer's open-source **WA1Tools v1.2**, authored for the
original PS1 Wild Arms, including the US release SCUS-94608:

- Repository: https://github.com/cebix/wa1tools
- Relevant modules: `wa/lzss.py`, `wa/archive.py`, `untrans`.
- License: **ISC**; the bounded `tools/wa1_lzss.py` implementation includes
  the required original copyright and permission/license notice.

The existing reference specifically reads the **first 0x3A000 bytes of
`BIN/CDFLR.BIN`** and identifies **two genuine in-game battle icon sheets**:

| Genuine texture | Compressed section | 16-color CLUT section | CLUT starting byte | Render dimensions |
| --- | ---: | ---: | ---: | --- |
| Battle icons / CONDITION GREEN / CHARGE UP | 49 | 48 | `0x120` | 256 × 256 |
| Battle icons / character statistics | 57 | 56 | `0x60` | 256 × 256 |

These are **known game assets** from published source, not visual guesses.
Both textures use packed **4 bits per pixel**, low nibble first, followed
by 16-color **PS1 BGR555** palette lookup. A zero 16-bit color is rendered
as **magenta placeholder** in the private PNG exporter (WA1Tools convention);
full original runtime alpha/STP semantics are *not* derived from this PNG.

## Actual privately held USA original resource evidence

The user's private `CDFLR.BIN` is 15,917,056 bytes and divides into **67
fixed 0x3A000-byte slots**. Every slot has eight candidate compressed
sections at indexes 43,45,47,49,51,53,55,57. The first u32 in every
stream is **0x8000 = 32,768 decoded bytes**. This is **now verified** as
a length prefix by the independent, specific WA1Tools implementation,
not merely a coincidental marker.

The authentic WA1 LZSS grammar is **not** the naive variant we correctly
rejected in Stage419:

- flags are low-bit first (bit 1 = one literal, bit 0 = one backreference);
- a two-byte backreference uses offset low 8 bits from first byte, offset
  upper 4 bits from **high nibble** of second byte;
- its length is **low nibble** of second byte **plus 3** (3–18 bytes);
- the 4096-byte dictionary starts zero-filled with its write cursor at
  `4096 - 18 = 4078`, copying overlapping references byte by byte.
- stop when the prefixed decoded byte count is met; source-end and output
  overshoot are both fatal in this stricter bounded implementation.

An exact independent local audit of all **536** original candidate streams
now yields:

| Category | Result |
| --- | ---: |
| Full 32,768-byte outputs decoded | **535 / 536** |
| Next-pointer-bounded streams ending within 0–3 spare bytes | **469 / 469** |
| Last (slot-end-only) sections decoding fully | **66 / 67** |
| Exceptions | **slot #4, section #57** — stream ends during a reference token |

The **one exception is not silently padded or declared corrupted**.
Slot #4 ends only 10,600 bytes after section #57 starts; the other
successfully decoded copies of that section consume 10,712 bytes.
This 112-byte difference is a useful diagnostic, not yet an explanation.
It may represent an intentionally unused/incomplete final resource or
a different recording/loader boundary. Do not run the decoder beyond the
fixed slot or invent the missing bytes.

Other decoded-content findings: section #47 and section #53 each produce
**one identical 32-KiB decoded output across all 67 slots**, even though
the encoded regions had 18 distinct SHA-256 fingerprints in Stage418.
Thus some encoded differences are non-semantic for pixel contents.
Section #49 also produces one decoded output for all 67 slots.
This distinction between *source-byte identity* and *decoded-output
identity* is important for choosing shared texture resources.

The private originals and outputs have NOT been placed in public GitHub.

## Actual local-only extracted outputs

A successful first-slot private extraction produced two **real**, paletted
256×256 PNGs:

- `battle_icons.png` — 9,185 encoded bytes consumed out of 9,188
  next-pointer-bounded bytes, 3 trailing bytes; decoded data SHA-256:
  `ae77a382f51586e55444c6dec903948b2ec093649fe61a4d6302b79b81ef7ff8`.
- `battle_icons2.png` — **10,712** encoded bytes consumed. The remaining
  slot bytes do NOT belong to that item without further evidence; decoded
  data SHA-256:
  `0e139771340584913adb6a3b2c7affde895a0885326119f8b795ce3fe1e404c2`.

Local extraction method:

```sh
python tools/audit_cdflr_verified_lzss.py /private/WildArms/CDFLR.BIN \
  > /private/WildArms/stage420-lzss-audit.json

# Install Pillow locally for the PNG exporter; no Pillow is required by
# the Python CI decoder/audit tests.
python -m pip install Pillow
mkdir -p /private/WildArms/verified-icons
python tools/export_wa1_battle_icons.py \
  /private/WildArms/CDFLR.BIN /private/WildArms/verified-icons
```

The PNG exporter **refuses to overwrite existing files**. It is only for
user-owned private original assets, never part of default public CI.
Do not commit PNG outputs, original ZIP, BIN/CUE, EXE, RAM dumps, scripts,
audio or textures into the public GitHub repository.

## CI and next steps

Public CI runs synthetic-only tests for literal/backreference operations,
reference overlapping and wrapping, zero-initialized dictionary, bounds,
output-size corruption, all eight section positions, last-slot truncation,
palette handling and low-nibble-first 4bpp indexing.

The first genuine graphics **are already decoded**, but they are icon sheets,
**not a reconstructed field/background scene**. Next verify representative
indexed texture/CLUT pairs across original slots, including exceptional
palette lengths at slot #4 and slot #28, and connect verified content IDs
to the Switch game rendering pipeline through **private local asset imports**.
A PS1 runtime trace is still needed to tie arbitrary slot indexes to maps,
and true original alpha/STP behavior still requires reference rendering.
