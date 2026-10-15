# BIN overlay header and MIPS opcode scan

Source: user's local **Wild Arms (USA)** MODE2/Form1 image. Only derived, non-asset metadata is committed.

| ISO file | Leading KSEG0-range words | First other word at byte offset | First other words |
| --- | ---: | ---: | --- |
| CDGD.BIN | 7 | 0x1c | 27bdffa0 afb20050 00a09021 afbf0058 |
| CDEF.BIN | 9 | 0x24 | 00000000 8017fc34 8017fc68 |
| CDFLR.BIN | 58 | 0xe8 | 00000000 00000000 00000000 |
| CDPL00.BIN | 61 | 0xf4 | 00000000 00000000 00000000 00000042 |
| CDPL01.BIN | 61 | 0xf4 | 00000000 00000000 00000000 00000042 |

In CDGD.BIN, at file offsets **0x1c through 0x34**, the words
`27bdffa0`, `afb20050`, `afbf0058`, `afb30054`, `afb1004c`,
`afb00048` match MIPS instructions that allocate stack space and save
callee-saved registers and the return address. This strongly suggests
executable MIPS code adjacent to the candidate pointer run.

**Caveats:** scanning values in KSEG0 address range alone does not prove
that they are pointers; recognizing instruction encodings does not prove
code reachability or runtime load addresses. The CDPL numeric fields are
not yet decoded, and **no resource boundaries** have been proven.

Reproduce without committing game assets:

```sh
python3 tools/inspect_disc.py "Wild Arms (USA).bin" --json > inventory.json
python3 tools/inspect_overlay_headers.py "Wild Arms (USA).bin" inventory.json \
  --paths '/BIN/CDGD.BIN;1' '/BIN/CDPL00.BIN;1' '/BIN/CDPL01.BIN;1'
python3 -m unittest discover -s tests -p 'test_*.py'
```
