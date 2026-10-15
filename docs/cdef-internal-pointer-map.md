# CDEF.BIN: candidate pointer table inside repeated code/data region

Source: user's own Wild Arms (USA) raw MODE2/Form1 image. Read-only inspection; no copyrighted assets included.

The 16 KiB candidate regions at `0x38000` and `0x3C000` share a 12 KiB prefix. Their **first 12 little-endian words** match in both copies.

Assuming **candidate** load base `0x8017C000`, all 12 map to offsets within the corresponding 16 KiB region. There are two distinct addresses among the 12 entries:

| Address | Relative offset | First 32-bit word at mapped target | Occurrences |
|---|---|---|---:|
| `0x8017C7F8` | `0x7F8` | `0x02402021` | 1 |
| `0x8017C84C` | `0x84C` | `0x9222018D` | 11 |

The two duplicated blocks agree at each pointer location and on the first word found at the mapped target. This is a **static consistency check**, not proof of the runtime load address, code execution, correct table length, or the meaning of either target.

Five synthetic local tests passed; the original-image comparison was separately executed.

Reproduce:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_cdef_overlay_pointers 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_audit_cdef_overlay_pointers.py' -v
```
