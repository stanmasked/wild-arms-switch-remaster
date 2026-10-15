# CDGD → WILDARMS.EXE: static MIPS call mapping

Verified locally against user-supplied **Wild Arms (USA)** raw BIN image. Only derived metadata is committed.

The ISO9660 file `/EXE/WILDARMS.EXE;1` starts with a valid PS-X EXE header:

- Main executable entry: `0x800B065C`
- Load address: `0x80011420`
- Payload size: `0xC1800` (792,576 bytes)
- Exclusive memory end: `0x800D2C20`
- Stack pointer: `0x801FFFF0`

Assuming the independently inferred CDGD overlay base `0x8017C000`, its candidate MIPS jumps in file range `0x1C..0x15B` resolve to:

| CDGD file offset | Instruction | Virtual target | Classification |
|---|---|---|---|
| 0x9C | JAL | 0x8006D258 | main EXE |
| 0xE0 | JAL | 0x8006DCA0 | main EXE |
| 0xEC | JAL | 0x8017C370 | CDGD overlay candidate |
| 0xF4 | J | 0x8017C300 | CDGD overlay candidate |
| 0x104 | JAL | 0x8006DCEC | main EXE |
| 0x150 | JAL | 0x8006DCEC | main EXE |
| 0x158 | J | 0x8017C300 | CDGD overlay candidate |

For a target in the main EXE, the byte position in its ISO file is
`0x800 + (target - 0x80011420)`, as PS-X EXE headers occupy 2048 bytes.

**Limits:** These are static instruction encodings and virtual-range matches.
No control-flow reachability, runtime module load, functional identity or
real execution has been established. A target lying in EXE memory range is
not, by itself, proof that it is a function entry point.

Reproduce:

```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/map_exe_calls.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

Do not commit the game disc or extracted proprietary executable content.
