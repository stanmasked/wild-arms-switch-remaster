# Original Wild Arms PS1 GP0 triangle packet layout candidates

## Evidence

A local audit of the user's original PS-X EXE loaded at `0x80011420` used the previously established `NCLIP -> MAC0/BLEZ -> SWC2 SXY0/1/2 -> OT` chains. Six sites contain OT packet tags with 4, 6, 7 or 9 GP0 command words after the one-word tag. The new `tools/audit_gp0_triangle_layouts.py` **also checks the relative SXY packet offsets** (not simply the packet word count).

| NCLIP site | GP0 words after tag | SXY0/SXY1/SXY2 byte offsets relative to tag | GP0 triangle layout candidate |
|---|---:|---|---|
| `0x80066E2C` | 9 | +8 / +20 / +32 | GT3 (shaded textured triangle) |
| `0x80066F64` | 9 | +8 / +20 / +32 | GT3 |
| `0x800670D8` | 7 | +8 / +16 / +24 | FT3 (flat textured triangle) |
| `0x800671F8` | 7 | +8 / +16 / +24 | FT3 |
| `0x800673B8` | 4 | +8 / +12 / +16 | F3 (flat untextured triangle) |
| `0x8006749C` | 6 | +8 / +16 / +24 | G3 (Gouraud untextured triangle) |

**All 6/6 packet layouts match.** The inferred families match the documented GPU GP0 polygon packet formats:

- F3: 4 words, GP0 command high byte 0x20..0x23.
- G3: 6 words, GP0 command high byte 0x30..0x33.
- FT3: 7 words, GP0 command high byte 0x24..0x27.
- GT3: 9 words, GP0 command high byte 0x34..0x37.

Reference: [psx-spx GPU Render Polygon Commands](https://psx-spx.consoledev.net/ps1/gpu/render-polygon-commands/).

## Confidence limitation

**These are structurally verified layout candidates, not decoded original GP0 command bytes.** A packet can have the expected number of words and SXY locations while its first GP0 opcode is populated or modified by a separate routine or data asset. The scanner explicitly reports `opcode_verified=false` and `observed_gp0_opcode=null`, and prints **expected** ranges rather than pretending to recover command bytes. To reach definitive identification, trace the write/initialization of the packet's first GP0 word (packet tag + 4) and any byte modification at tag + 7.

The analysis is static; other control-flow branches may affect which paths run. No original game binaries, packet contents, assets or textures were committed.

## Reproduction

With a locally extracted, privately held `WILDARMS.EXE`:

```sh
python3 tools/audit_gp0_triangle_layouts.py /private/path/WILDARMS.EXE
```

On the original local EXE: 8 NCLIP sites, six OT packet links, all six layouts matched (GT3=2, FT3=2, F3=1, G3=1). Six Python regression tests reject wrong offsets, mixed base registers, duplicate/missing coordinates and unsupported packet lengths.

Complete local CMake C++20 build and CTest finished: **33/33 suites passed**. GitHub Actions, complete GTE hardware accuracy and a playable native Nintendo Switch port have not been established.
