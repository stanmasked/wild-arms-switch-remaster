# Global pointer 0x800D2C3C — exact-reference audit

Original image: user-owned Wild Arms (USA), read locally using raw 2352-byte MODE2/Form1 sectors. No proprietary assets are committed.

- Main PS-X EXE load range: `[0x80011420, 0x800D2C20)`.
- Address `0x800D2C3C` is **0x1C bytes past the load image end**.
- **39 exact adjacent** `LUI reg,0x800D` + `LW reg2,0x2C3C(reg)` references found in loaded EXE instructions.
- **0 exact adjacent store** sequences to that address detected.
- Examples: `0x8004932C` / `0x80049330`, `0x8006D278` / `0x8006D27C`, `0x8006DCC0` / `0x8006DCC4`, `0x8006DD0C` / `0x8006DD10`, `0x80071018` / `0x8007101C`.

The location *may* be in an uninitialized/global region beyond the image payload. **It is not enough to prove it is BSS**, nor that it points to a particular gameplay structure.

**Method limitations:** strict adjacent pairs only; separate `LUI` and load/store instructions, temporary register copies, computed addresses, indirect writes, overlay code, and runtime initialization are not covered. No conclusion that the global is never written is justified.

Reproduce:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/find_global_refs.py 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Next investigation: non-adjacent references, address construction, writes through base registers and runtime initialization.
