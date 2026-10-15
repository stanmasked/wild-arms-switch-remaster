# Original Wild Arms polygon winding: PS-X EXE evidence

## Source and scope

Audited the **user-provided original Wild Arms PS1 disc**, kept **only in the local workspace**. The ISO9660 file `/EXE/WILDARMS.EXE;1` has a 2048-byte PS-X EXE header, load address `0x80011420`, declared load size `0xC1800`. Scanned aligned instructions of the original load image for COP2 GTE commands. **No game binary, original model, or proprietary asset is committed to GitHub.**

A repeatable scanner, `tools/audit_original_nclip_winding.py`, expects a **locally extracted PS-X EXE**, not a raw CD-sector disc image. It outputs only opcode addresses, nearby branch addresses and summary counts; it does not reproduce game code.

## Confirmed static results

- `RTPT` (COP2 function 0x30): **11** matching instruction words.
- `NCLIP` (COP2 function 0x06): **8** matching instruction words.
- **6 of those 8 NCLIP sites** have a nearby `MFC2` read from GTE data register 24 (MAC0), followed by `BLEZ` on the same CPU register (branch if signed MAC0 <= 0).

| NCLIP address | MFC2 MAC0 | BLEZ MAC0 | BLEZ target |
|---|---|---|---|
| `0x80066E2C` | `0x80066E3C` | `0x80066E44` | `0x80066EAC` |
| `0x80066F64` | `0x80066F74` | `0x80066F7C` | `0x8006702C` |
| `0x800670D8` | `0x800670E8` | `0x800670F0` | `0x80067144` |
| `0x800671F8` | `0x80067214` | `0x8006721C` | `0x80067294` |
| `0x800673B8` | `0x800673C8` | `0x800673D0` | `0x80067424` |
| `0x8006749C` | `0x800674AC` | `0x800674B4` | `0x80067508` |

The remaining matching NCLIP sites are `0x800772A8` and `0x8007757C`; the same MAC0/branch pattern was not found within the selected 10-instruction window.

## Meaning for geometry

**Six sites check the signed condition `MAC0 <= 0` and branch on it.** Thus the non-branch path requires `MAC0 > 0`. This is strong static evidence for a **positive NCLIP winding convention in these paths**, subject to full control-flow verification of which branch actually skips rendering. It does **not** establish that every polygon uses this rule, or that this code is always executed at runtime.

The `FrontFace::PositiveArea` option in `include/gte_triangle_classification.hpp` is now evidence-supported for these six code paths. **No universal default or global backface-culling switch was changed.** Original assets still require independent checks for winding and near-plane clipping.

## Reproduce and verification

Extract `/EXE/WILDARMS.EXE;1` **locally** from a disc owned by the user and run:

```sh
python3 tools/audit_original_nclip_winding.py /private/path/WILDARMS.EXE
```

The offline local audit of the user's original disc reproduced all counts and addresses above. The dedicated synthetic opcode parser has **5/5 unittest checks passing**. A complete locally staged CMake/GCC build passed **30/30 CTest suites**, including the new `wa_original_nclip_winding_audit` target. These tests verify static opcode pattern matching, not console execution or full hardware fidelity. GitHub Actions and Switch-native game execution remain unverified.
