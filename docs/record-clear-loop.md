# Confirmed 16-element clearing loop in Wild Arms (USA)

A read-only check against the user-owned original PS1 BIN image located the complete 11-word routine at virtual address **0x80078D84** in `WILDARMS.EXE`.

| Address | MIPS instruction | Meaning |
|---|---|---|
| 0x80078D84 | `lui v1,0x800d` | Form global address |
| 0x80078D88 | `lw v1,0x2c44(v1)` | Load array pointer |
| 0x80078D8C | `addiu v0,zero,15` | Initialize counter to 15 |
| 0x80078D90 | `sb zero,0(v1)` | Clear first byte of current element |
| 0x80078D94 | `addiu v0,v0,-1` | Decrement counter |
| 0x80078D98 | `bgez v0,-3` | Return to byte store while counter nonnegative |
| 0x80078D9C | `addiu v1,v1,88` | **Delay slot**: advance pointer, even on final iteration |
| 0x80078DA0 | `lui at,0x800d` | Set up additional global |
| 0x80078DA4 | `sw zero,0x2eb0(at)` | Clear global at **0x800D2EB0** |
| 0x80078DA8 | `jr ra` | Return |
| 0x80078DAC | `nop` | Delay slot |

**Observed semantics:** clear byte 0 at offsets `0, 88, 176, …, 1320` from the runtime pointer stored at `0x800D2C44` — exactly **16 elements**. The pointer in `v1` is incremented to `base+1408` on the final branch delay slot, but **no store occurs at that offset**.

This establishes a 16-element **clear operation**, not necessarily a total array capacity or type identity. The base pointer's origin remains unknown. The surrounding entry initializer at `0x80078DB0` separately uses the same 88-byte step.

Verification: original BIN check passed, plus five synthetic tests. No original executable or assets committed.

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_record_clear 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_record_clear.py' -v
```
