# Secondary indexed array via 0x800D2CEC (Wild Arms USA)

This report describes a **read-only analysis of the user-owned original PS1 image**. No game binaries, audio, images, or other proprietary assets are committed.

The fully loaded `WILDARMS.EXE` image (792,576 bytes) contains **two** exact *adjacent* `LUI`+`LW` sequences for global address `0x800D2CEC`:

| LUI PC | LW PC | Subsequent behavior |
|---|---|---|
| `0x80078D18` | `0x80078D1C` | `a2 = memory32[0x800D2CEC] + 24 * v1`; `jal 0x800776F0` with final `addu a2,v0,a2` in delay slot |
| `0x80078E30` | `0x80078E34` | `s0[0x54] = memory32[0x800D2CEC] + 24 * a0` (32-bit store) |

At `0x80078D20–0x80078D28`, the three instructions `sll a2,v1,1; addu a2,a2,v1; sll a2,a2,3` establish **24 times the v1 index**. The `jal 0x800776F0` at `0x80078D2C` executes `addu a2,v0,a2` in its branch delay slot; this final addition incorporates the base pointer already loaded in `v0`.

The second occurrence at `0x80078E38–0x80078E4C` was previously established independently as the source of field `+0x54` in an 88-byte-stride record.

**Limits:** 24 bytes is a measured address stride, not proof of item layout, extent, allocation count, or gameplay role. The strict pair scan does not find initialization via indirect addressing, nonadjacent construction, or other files. Runtime execution is not confirmed.

Reproduction:
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.audit_secondary_array 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_audit_secondary_array.py' -v
```

Verified on the original image: **15 exact instruction words**. Six local synthetic unit tests passed.
