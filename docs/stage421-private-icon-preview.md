# Stage421 — private authentic PS1 icon sheets in the Switch field renderer

## Scope: first genuine art, without touching gameplay

Stage420 verified two original **256×256, 4bpp, 16-color PS1 battle
icon sheets** extracted from the user-provided Wild Arms (USA) CDFLR.BIN
using the WA1Tools-documented LZSS format (Christian Bauer, ISC).
Original files and actual art **are not** included in this repository.

Stage421 adds a **deliberately opt-in** bridge that can display those
textures on the already existing libnx RGBA8888 framebuffer in the
Nintendo Switch field prototype. The default NRO, battle UI, encounter
selection, NeXium replay frames and save formats are **unchanged**.

### Format WAIC v1 (remake-only, NOT original PlayStation data)

All integers are little-endian.

| Offset | Bytes | Meaning |
| ---: | ---: | --- |
| 0 | 4 | ASCII `WAIC` |
| 4 | 4 | Version = 1 |
| 8 | 2 | Width = 256 |
| 10 | 2 | Height = 256 |
| 12 | 2 | Exactly 16 palette entries |
| 14 | 2 | Reserved = 0 |
| 16 | 4 | Payload length = 65,600 |
| 20 | 4 | CRC32/ISO-HDLC of palette + indices |
| 24 | 64 | 16 RGBA8888 palette entries, alpha = 255 |
| 88 | 65,536 | Row-major 8-bit indexed pixels, each 0..15 |

**Total file size is exactly 65,624 bytes.** Palette RGBA storage uses
the same byte order as the existing `wa::field::rgba()` framebuffer.
Index bytes are deliberately expanded from original packed 4bpp:
the renderer does not perform any runtime LZSS decompression or PS1
format inference.

CRC32 detects accidental corruption but is **not** authentication or
proof of resource provenance.

The inspection image is **fully opaque**. This is intentional:
a zero PS1 color value is rendered as a magenta placeholder as in the
Stage420/Wa1Tools PNG export, not yet the game's correct transparent/STP
pixel behavior. It must **not** be mistaken for faithful battle HUD
compositing or final artwork.

### Produce your own private WAIC files

From the previously verified **private** first-slot indexed PNGs:

```sh
python -m pip install Pillow
mkdir -p "/private/wildarms-icons"
python tools/pack_private_waic.py \
  "/private/battle_icons_ps1_original_private.png" \
  "/private/wildarms-icons/battle_icons.waic"
python tools/pack_private_waic.py \
  "/private/battle_icons2_ps1_original_private.png" \
  "/private/wildarms-icons/battle_icons2.waic"
```

The converter accepts only `P` mode PNGs with exactly 256×256 pixels,
16 used palette indices (0..15), RGB palette, and no custom alpha.
It uses exclusive-create mode and refuses overwrites. It never
upscales, interpolates, changes the index mapping or guesses STP.

### Install on your own Switch SD (private assets)

Copy the two files, preserving their names, to:

```text
sdmc:/switch/wild_arms_field/assets/private/battle_icons.waic
sdmc:/switch/wild_arms_field/assets/private/battle_icons2.waic
```

The directory is **not** created by the game; create it on your own SD.
Neither the normal NRO nor CI creates/copies these assets.

Build the optional diagnostic NRO separately:

```sh
make -C switch WA_PRIVATE_ICON_PREVIEW=1
```

In manual field mode (not autoplay or battle), **hold Right Stick click**
to display original icon sheet 1 at exactly 256×256 in the center of the
1280×720 framebuffer. Hold **Right Stick click + Left Stick click** to
inspect sheet 2. Releasing returns to the normal field. Missing,
truncated, oversized or CRC-invalid private resources display nothing
and do not affect gameplay. Both icons are read at startup only.

Without `WA_PRIVATE_ICON_PREVIEW=1`, all loading and drawing code is
**excluded at compile time**, preserving ordinary builds.

### Safety and acceptance gates

- C++ `include/field_private_icon.hpp`: strict file size/schema/CRC/
  palette-index/opaque-alpha validation before any use; a failed draw
  never changes the framebuffer, even for a manually invalid object.
- C++ `tests/test_private_icon.cpp`: fully synthetic container,
  corruption and raster-geometry tests, independent of libnx and artwork.
- Python `tests/test_pack_private_waic.py`: fully synthetic deterministic
  packing and CRC tests, no Pillow requirement in CI.
- The index preview is diagnostic only. Original STP transparency,
  original texture placement/tile arrangement, and background scenery
  still require PS1 reference-frame validation.

## Correct source for reconstructing original field locations

Independent public WA1Tools `mapinfo` reads **128 map blocks** from
`BIN/CDSTG.BIN` with **stride 0x91000** (593,920 bytes), skipping
**map #25** as intentionally disabled. Its `wa/map.py` reports the
embedded map-graphics region beginning at **offset 0x15000** within
those map blocks. The map-related PS1 memory address is
`0x8014F000`, distinct from CDFLR's tentative buffer `0x80183000`.

Thus the path to an authentic *field scene* is to investigate the actual
**CDSTG map graphics + layout** from this separately documented format,
rather than incorrectly calling the CDFLR battle-icon sheets a map.
No specific gameplay locale/scene has yet been identified or imported.

Upstream format/source reference:
https://github.com/cebix/wa1tools (`mapinfo`, `wa/map.py`,
`wa/lzss.py`, `untrans`).

Never push the original image, CDSTG/CDFLR, icon PNGs, WAIC files,
debugger RAM dumps, or game screenshots to the public GitHub repository.
