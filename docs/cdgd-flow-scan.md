# CDGD.BIN — initial MIPS flow scan

Source: user-owned Wild Arms (USA) PS1 disc image, scanned locally in read-only mode. No binary assets committed.

Candidate MIPS instruction region begins near file offset `0x1c`, immediately after seven apparent KSEG0 addresses. Scanning 0x140 bytes from there found ten control-flow instructions, including:

| Offset | Opcode | Resolution |
|---|---|---|
| 0x64 | BEQ | Relative file offset 0x300, **conditional on continuous code mapping** |
| 0x80 | JR v0 | Indirect register jump, absolute target unknown |
| 0x9c | JAL | 26-bit target field 0x001b496 |
| 0xe0 | JAL | Target field 0x001b728 |
| 0xec | JAL | Target field 0x005f0dc |
| 0xf4 | J | Target field 0x005f0c0 |
| 0x104 | JAL | Target field 0x001b73b |
| 0x134 | BNE | Relative file offset 0x300, **conditional on continuous code mapping** |
| 0x150 | JAL | Target field 0x001b73b |
| 0x158 | J | Target field 0x005f0c0 |

**Interpretation limits:** Scanning words is not a control-flow graph or proof of code reachability. The branch targets above use the hypothetical file-offset-is-PC-offset assumption; instruction encoding does not independently confirm this. Full J/JAL virtual addresses require runtime PC upper bits, and mapping back to disc bytes requires establishing the overlay load address.

Reproduce (local copy of user-owned disc required):
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/scan_mips_flow.py 'Wild Arms (USA).bin' inventory.json --start 0x1c --length 0x140
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
