# Full-sector XA classification (local user-owned Wild Arms USA image)

Read-only pass across every sector in three ISO9660 file extents. Sector classes identified from XA submode bytes (data=0x08, audio=0x64/0xe4, video=0x42/0xc2, empty=0x00, end=0x80).

| File | Extent sectors | XA audio | XA video | Empty/other |
| --- | ---: | ---: | ---: | ---: |
| E00.IXA | 1,208 | 393 (385 x 0x64, 8 x 0xe4) | 0 | 815 |
| M00.IXA | 28,600 | 13,325 (13,317 x 0x64, 8 x 0xe4) | 0 | 15,275 |
| WAOP.STR | 20,233 | 2,463 | 17,704 (17,703 x 0x42, 1 x 0xc2) | 66 |

Observed audio coding byte: 0x01. Observed video coding byte: 0x80.
This is a sector classification, not proof of successful decoding.
No game assets are included here.

First payload bytes of CDEN.BIN: `00 01 1d 80 f8 01 1d 80 f8 03 1d 80`.
First payload bytes of CDSTG.BIN: `24 f6 15 80 00 00 00 00 40 f0 14 80`.
These are not yet identified as a resource archive header.
