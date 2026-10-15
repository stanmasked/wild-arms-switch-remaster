# Wild Arms (USA) — origin of record field +0x54

Verified with the original user-owned raw MODE2/Form1 disc image. No proprietary image or extracted assets have been committed.

Eight exact 32-bit MIPS instruction words in `WILDARMS.EXE` at `0x80078E30–0x80078E4C` reproduce:

| PC | MIPS operation | Effect |
|---|---|---|
| 0x80078E30 | `lui v1,0x800D` | Prepare global address |
| 0x80078E34 | `lw v1,0x2CEC(v1)` | Read global `0x800D2CEC` |
| 0x80078E38 | `sll v0,a0,1` | Compute `2*a0` |
| 0x80078E3C | `addu v0,v0,a0` | Compute `3*a0` |
| 0x80078E40 | `sll v0,v0,3` | Compute `24*a0` |
| 0x80078E44 | `addu v1,v1,v0` | Base pointer plus index*24 |
| 0x80078E48 | `addu v0,s0,zero` | Set return value to record pointer |
| 0x80078E4C | `sw v1,0x54(s0)` | Store computed value in record field `0x54` |

Thus **record[0x54] = memory32[0x800D2CEC] + 24*a0 (mod 2^32)** in this code path.

This suggests an address of a second indexed data collection, but **the target allocation, item count, semantic meaning and safety of dereferencing it are not known**. The caller has a verified record index step of `0x58` (88 bytes), distinct from the `0x18` (24-byte) step observed here.

Verification: direct image signature matched; six synthetic unit tests passed locally.

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_record_field54_origin 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_audit_record_field54_origin.py' -v
```
