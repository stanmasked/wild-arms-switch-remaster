# CDEF.BIN repeated 2 KiB-aligned regions

Read-only investigation of the user's **Wild Arms (USA)** disc image. These are comparisons of binary bytes, not verified runtime functions or relocations.

- File: `/BIN/CDEF.BIN;1`; ISO logical size **372,736 bytes**.
- Prefixes at file offsets `0x38000` and `0x3C000` match for **0x3000 bytes** (12,288 bytes) and diverge immediately thereafter.
- Pairs of 12 KiB repeated regions also begin at `0x1C000` and `0x20000`; `0x2A000` and `0x2E000`; and `0x31000` and `0x35000`.
- Repeated regions in these examples are shifted by **0x4000** (16,384) bytes. No completely identical 16 KiB-aligned region was found in a 2 KiB-aligned exhaustive comparison.
- Observed candidate global loads at `0x38778`, `0x39744`, `0x39928` are repeated at exactly `+0x4000`.

**Interpretation:** repeated code/data blocks are likely deliberate, but whether they represent loaded variants, duplicated routines, or compression/packing is not known. Avoid claiming to have derived the runtime load address from these matches. Raw binary and gameplay assets remain off GitHub.

Reproduce locally:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.find_repeated_regions 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py'
```
