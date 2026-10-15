# Global pointer `0x800D2C44`: verified exact-reference inventory

Input: user-owned `Wild Arms (USA).bin`, original raw 2352-byte-sector MODE2/Form1 disc image. Analysis performed locally; **no game assets uploaded**.

Scanned **792,576 loaded code/data bytes** of `/EXE/WILDARMS.EXE;1`, requiring strictly adjacent MIPS `LUI` + `LW`/`SW` pairs that encode an access to `0x800D2C44`.

| LUI PC | Memory operation PC | Operation |
|---|---|---|
| `0x80078B48` | `0x80078B4C` | `LW` |
| `0x80078D84` | `0x80078D88` | `LW` |
| `0x80078DD0` | `0x80078DD4` | `LW` |
| `0x80078F80` | `0x80078F84` | `LW` |
| `0x8007915C` | `0x80079160` | `LW` |
| `0x80086CD4` | `0x80086CD8` | `LW` |

**Observed: 6 loads, 0 stores** in this *strict adjacent-pair scan*.
One of them at `0x80078DD0` is inside the previously analyzed indexed initializer caller `0x80078DB0`, which computes stride `0x58` (88 bytes) before passing record+4 to the initializer `0x8006CE70`.

**Scope / uncertainty:** zero adjacent stores does **not** imply the pointer is never written. The scan excludes nonadjacent address construction, indirect stores, boot-loader operations and code in BIN overlays. It also does not demonstrate the meaning, allocation size or live value of the pointer. The PS-X EXE header does not declare a BSS range.

Reproduction:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 tools/find_global_refs.py 'Wild Arms (USA).bin' inventory.json --address 0x800d2c44
python3 -m unittest discover -s tests -p 'test_global_pointer_2c44.py' -v
```

The five synthetic regression tests use existing `tools/find_global_refs.py`, so CI does not require copyrighted inputs.
