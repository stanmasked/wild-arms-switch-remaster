# Indexed initializer caller — WILDARMS.EXE 0x80078DB0

Static read-only analysis of the user's own **Wild Arms (USA)** raw CD image.

The caller at `0x80078DB0` computes `v0 = 88 * a0` (where `a0` initially contains the index), loads a global base pointer through `0x800D2C44`, and adds that offset to form `s0`, the candidate record address.

The following signature is present in the verified original EXE:
- `sb 1, 0(s0)` (the value 1 is first placed in `v0`).
- `addiu a0,s0,4`; `jal 0x8006CE70`.
- `sb a2,1(s0)` is the **JAL delay slot**, executed before control enters the callee.
- Additional direct stores in the caller include `sh` at offsets `0x02`, `0x52`, `sb` at `0x50`, and `sw` at `0x54` relative to `s0`.

The callee `0x8006CE70` receives a pointer offset by **+4**, and writes fields at offsets 4–36 relative to that pointer (hence offsets 8–40 relative to `s0`). This is the first directly linked initialization sequence with specific bytes and word widths, rather than an inferred structure from address patterns alone.

**Caveat:** A stride of 88 does not itself prove that each record owns exactly 88 bytes, and the number or meaning of records is unknown. Additional stores in caller may use data from other global tables, and interpreting their values requires deeper register tracking. Function reachability in-game is also unconfirmed.

Reproduce on locally owned image:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.verify_indexed_init_call 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_verify_indexed_init_call.py' -v
```
No game executable or assets are committed.
