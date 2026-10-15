# Secondary array callee: first verified MIPS instructions

Source: user's own **Wild Arms (USA)** PS1 image. Verified by reading the ISO9660 `/EXE/WILDARMS.EXE;1` payload from raw MODE2/Form1 sectors; no copyrighted assets committed.

The caller at `0x80078D2C` invokes `0x800776F0` and passes `base_0x800D2CEC + 24 * index` in argument register `a2` (computed in the caller's JAL delay slot).

Verified callee instructions:

| Virtual PC | MIPS | Interpretation |
|---|---|---|
| 0x800776F0 | `addiu sp,sp,-96` | Stack frame |
| 0x800776F8 | `addu s7,a0,zero` | Save first argument |
| 0x80077700 | `addu s6,a2,zero` | Save secondary-array pointer |
| 0x80077708 | `addu s5,a3,zero` | Save fourth argument |
| 0x8007772C | `lh v0,0x52(s7)` | **Signed** 16-bit load |
| 0x80077730 | `lw s1,0(a1)` | Read 32-bit word through second argument |
| 0x80077734 | `beq v0,zero,0x800778AC` | Conditional branch |
| 0x80077768 | `jal 0x800B70E8` | Helper call |
| 0x80077780 | `jal 0x800B70E8` | Repeated helper call |

**Correction:** The signed halfword opcode is `0x86E20052` (`LH`), not unsigned `LHU`. An initial synthetic-only run passed with the wrong opcode, but the real-image signature test caught the mismatch. After correction the signature passed on the original image and six local synthetic tests passed. Use `int16_t` semantics when reconstructing this load.

The function's actual runtime reachability, argument ownership, allocation bounds, and gameplay purpose remain unknown. These nine instruction matches do not establish a complete function semantics or C++ port.

Reproduce:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_secondary_callee 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_secondary_callee.py' -v
```
