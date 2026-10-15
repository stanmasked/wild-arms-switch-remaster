# Verified MIPS structure initializer in WILDARMS.EXE

Read-only static verification on the user-owned **Wild Arms (USA)** PlayStation image. No copyrighted game executable bytes are committed; the instruction signatures below are short numeric metadata required to reproduce the finding.

At virtual address **0x8006CE70** in main `WILDARMS.EXE`:

- `addiu v0,zero,0x1000`
- `sh zero,8(a0)`, `sh zero,6(a0)`, `sh zero,4(a0)`
- `sw zero,0x10(a0)`, `sw zero,0x0C(a0)`, `sw zero,0x14(a0)`
- `sw v0,0x1C(a0)`, `sw v0,0x20(a0)`
- `jr ra` followed by **delay-slot** `sw v0,0x24(a0)`

That establishes a bounded, 11-instruction function-shaped region which initializes nine offsets from input pointer `a0`. The three final words are set to `0x1000`. **No role for the object is yet established.** The overlapping stores were checked for instruction widths (3 x halfword, 6 x word), and neighboring code after the delay slot is excluded.

The caller at candidate main-EXE address `0x80078DB0` contains a static JAL to this address. Runtime reachability, original C source semantics, and function name remain unknown.

Reproduce locally:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_exe_initializer 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_exe_initializer.py' -v
```

This verification is limited to the original image variant. Other releases may have different code addresses.
