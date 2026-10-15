# Geometry Transform Engine helper found in Wild Arms USA

**Source of evidence:** 11 exact 32-bit instruction words at virtual address `0x800B70E8` in the original, user-owned `Wild Arms (USA).bin`, read from ISO9660 PS-X EXE file inside a raw MODE2/Form1 CD image. This is verified *static* behavior, not a runtime execution trace.

| Address | MIPS / GTE instruction | Result |
|---|---|---|
| `0x800B70E8` | `LWC2 $0,0(a0)` | Load GTE vector register VXY0 |
| `0x800B70EC` | `LWC2 $1,4(a0)` | Load GTE vector register VZ0 |
| `0x800B70F0` | `NOP` | Pipeline spacing |
| `0x800B70F4` | `COP2 0x4A180001` | GTE **RTPS** single-point rotation/translation/perspective, `sf=1`, `lm=0` |
| `0x800B70F8` | `SWC2 $14,0(a1)` | Write GTE SXY2 projected screen coordinates to caller buffer |
| `0x800B70FC` | `SWC2 $8,0(a2)` | Write GTE IR0 (interpolation/depth-cue intermediate) |
| `0x800B7100` | `CFC2 v1,$31` | Read GTE FLAG control register |
| `0x800B7104` | `MFC2 v0,$19` | Read GTE SZ3 (depth) |
| `0x800B7108` | `SW v1,0(a3)` | Write GTE flags to caller buffer |
| `0x800B710C` | `JR ra` | Return |
| `0x800B7110` | `SRA v0,v0,2` | Return-delay-slot: arithmetic right shift of depth |

This helper is called twice within the previously studied main-EXE function `0x800776F0`. The finding demonstrates that the path uses the **PlayStation GTE**, not just generic 24-byte array arithmetic. Recovering caller-provided transformation matrices, registers, projection settings, and exact fixed-point overflow behavior remains necessary.

For the native Switch port, implement a clean C++ equivalent of the **RTPS mathematical contract**, with fixed-point arithmetic, saturation and GTE flags verified against original output samples; merely converting opcodes or using unrestricted floating-point math will not guarantee equivalent graphics.

## Local reproduction
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_gte_rtps 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_gte_rtps.py' -v
```

Original image verification and six synthetic local regression tests passed. GitHub Actions status has not been independently verified. No proprietary game assets were uploaded.
