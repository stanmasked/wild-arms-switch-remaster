# CDEF.BIN paired-region tail audit (Wild Arms USA)

Read-only exact-byte comparison of known repeated regions, performed on the user-owned original 2352-byte-sector MODE2/Form1 disc image. No copyrighted game bytes committed.

Each pair starts **0x4000 (16,384) bytes apart** and has an identical **0x3000-byte (12 KiB)** prefix.

| Offset A | Offset B | Tail bytes compared | Differing bytes |
|---|---|---:|---:|
| 0x1C000 | 0x20000 | 4096 | 3564 |
| 0x2A000 | 0x2E000 | 4096 | 3646 |
| 0x31000 | 0x35000 | 4096 | 3517 |
| 0x38000 | 0x3C000 | 4096 | 3492 |
| 0x46000 | 0x4A000 | 4096 | 3473 |
| 0x4D000 | 0x51000 | 4096 | 3592 |
| 0x54000 | 0x58000 | **0** | **not available** |

**Correction to prior interpretation:** `CDEF.BIN` is exactly 372,736 bytes (`0x5B000`). Its last paired occurrence, starting at `0x58000`, only contains the 12-KiB shared prefix before the file ends. A distinct 4-KiB tail is **not present** there and must not be inferred.

Some differing tails contain little-endian words encoding familiar MIPS R3000 instructions, including stack adjustment and register loads/stores, but there is not yet proof of runtime reachability or a load address. Repetition plus MIPS-like opcode patterns does not establish executable module boundaries.

Local verification: five synthetic unit tests passed; observed counts above were calculated directly from the original BIN image.

Reproduction:

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/compare_cdef_tails.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_compare_cdef_tails.py' -v
```

Next: search for relocation/address tables and map the repeated regions to candidate runtime overlays before attempting interpretation as game functions.
