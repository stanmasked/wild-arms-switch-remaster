# Original Wild Arms: NCLIP branch to polygon-coordinate writes

## Original data and evidence

Examined the **local original** `/EXE/WILDARMS.EXE;1`, loaded at `0x80011420`. Only opcode addresses and derived results are published. The proprietary PS-X EXE, original disc and game assets remain local.

The previous static audit found 8 GTE `NCLIP` instructions, 11 `RTPT` instructions, and six nearby `NCLIP → MFC2 MAC0 → BLEZ MAC0` sequences. This continuation decodes the instructions *between* the `BLEZ` delay slot and its forward branch target. All six intervals contain `SWC2` (opcode 0x3A) writes from the screen-coordinate data registers **12=SXY0**, **13=SXY1**, **14=SXY2**. The writes use the same base CPU register 11, but the packet-coordinate field offsets vary among code paths.

| NCLIP | BLEZ (MAC0 <= 0) | Skip target | SWC2 offsets SXY0/SXY1/SXY2 |
|---|---|---|---|
| `0x80066E2C` | `0x80066E44` | `0x80066EAC` | +8 / +20 / +32 |
| `0x80066F64` | `0x80066F7C` | `0x8006702C` | +8 / +20 / +32 |
| `0x800670D8` | `0x800670F0` | `0x80067144` | +8 / +16 / +24 |
| `0x800671F8` | `0x8006721C` | `0x80067294` | +8 / +16 / +24 |
| `0x800673B8` | `0x800673D0` | `0x80067424` | +8 / +12 / +16 |
| `0x8006749C` | `0x800674B4` | `0x80067508` | +8 / +16 / +24 |

**Interpretation:** the taken BLEZ path (`MAC0 <= 0`) skips the direct fallthrough interval containing these SXY writes. This supports a **positive signed NCLIP area** convention for this group of polygon-building paths, not necessarily every polygon in the entire game.

This is static instruction evidence, **not** full MIPS control-flow or runtime reachability analysis. Some intervals have additional conditional branches and jumps. Even on the positive path, not every in-range instruction is guaranteed to execute. A complete proof of successful primitive submission requires following subsequent packet linkage, DMA ordering/OT writes, or execution traces. No renderer culling behavior was globally changed.

## Reproduce without committing original game assets

Using an extracted private PS-X EXE:

```sh
python3 tools/audit_nclip_polygon_writes.py /private/path/WILDARMS.EXE
```

Requires the previously committed `tools/audit_original_nclip_winding.py`. The script scans the MIPS instructions, decodes `SWC2` register/base/signed offset, skips the MIPS branch-delay slot, and only counts complete SXY0/SXY1/SXY2 triplets before the BLEZ forward target.

## Verification

- The offline scan of the real local PS-X EXE yielded **8 NCLIP, 6 MAC0 BLEZ chains and 6 SXY-triplet fallthrough intervals**.
- `tests/test_nclip_polygon_writes.py`: **5/5** synthetic instruction tests passed, including branch delay-slot exclusion, backward branch, non-COP2 `SW` and signed offset decoding.
- A fresh local CMake/GCC build of the staged full host project passed **31/31 CTest suites**, including `wa_original_nclip_polygon_writes`.

These verifications concern instruction pattern interpretation, not PlayStation hardware GTE fidelity, Switch-native execution, or verified GitHub Actions CI. No original Wild Arms code bytes were uploaded.
