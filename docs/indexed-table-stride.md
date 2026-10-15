# EXE indexed table: measured stride and accesses

Source: user's own **Wild Arms (USA)** raw MODE2/Form1 image. Only derived metadata committed.

Three candidate routines at `0x8006D258`, `0x8006DCA0`, and `0x8006DCEC` share an identical index-calculation prefix (MIPS).

Exact arithmetic in `v0`, starting with `a1`:
- `sll v0,a1,2` => 4a1
- `addu v0,v0,a1` => 5a1
- `sll v0,v0,1` => 10a1
- `addu v0,v0,a1` => 11a1
- `sll v0,v0,2` => 44a1
- `addu v0,v0,a1` => 45a1
- `sll v0,v0,1` => 90a1
- `addu v0,v0,a1` => 91a1
- `sll v0,v0,2` => **364a1 = 0x16C times index**

All load a pointer through `lui v1,0x800d; lw v1,0x2c3c(v1)`, therefore **memory location `0x800D2C3C` stores a runtime base pointer**, under conventional MIPS semantics.

Addresses accessed from the computed record base in these routines include:

| Offset | MIPS operation | Meaning |
| --- | --- | --- |
| `0xA44` | `sb` and `lbu` | Flag byte (two routines modify bits, exact purpose unknown) |
| `0xA4C` | `sh` | 16-bit field set to zero in one routine |
| `0xA4F` | `sb` | 8-bit field set from `a2` in one routine |
| `0xA50` | `sb` | Byte assigned `0xff` in one conditional path |
| `0xA54` | `sb` | Byte assigned `a0` in the first routine's branch-delay slot |

**Critical caution:** `0xA44` and higher offsets greatly exceed stride `0x16C`. It is therefore **not justified to call this a standalone 364-byte record with those fields**. This could be a structure-of-arrays layout, a large per-index buffer, or another compound layout. The 364-byte *index step* is verified, but record boundaries, ownership and runtime pointer validity are not. MIPS branch-delay-slot stores must be interpreted carefully.

Reproduction using locally owned image:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/verify_record_stride.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
