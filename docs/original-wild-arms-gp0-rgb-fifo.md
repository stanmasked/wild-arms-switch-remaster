# Original Wild Arms: GTE RGB FIFO writes to GT3 polygon colors

## New evidence from the original EXE

A static audit of the user's original, **locally held** `WILDARMS.EXE` (PS-X load address `0x80011420`) examines the six previously identified `NCLIP → MAC0/BLEZ → SXY → GPU packet → OT` code regions. **No original game binary, models, textures or proprietary packet contents were committed.**

In the `0x80066F64` polygon-processing path (GT3 layout candidate), three consecutive MIPS `SWC2` instructions store the PlayStation GTE **color FIFO registers** (data registers 20, 21 and 22) into a polygon packet:

| Store instruction | GTE register | GPU packet tag-relative byte offset | GP0 purpose |
|---|---|---:|---|
| `0x80066FBC` | RGB0 (data 20) | +4 | First Gouraud color and command-byte position |
| `0x80066FC0` | RGB1 (data 21) | +16 | Second Gouraud vertex color |
| `0x80066FC4` | RGB2 (data 22) | +28 | Third Gouraud vertex color |

The same path subsequently uses `LBU` from `packet+7` and `SB` to `packet+7`. Thus the first RGB0 word occupies the GP0 command/color word, and the opcode byte is explicitly restored. **This identifies the source of the dynamic vertex colors on one GT3 path, not the initial GP0 opcode value itself.**

## Coverage and limits

The scanner `tools/audit_gp0_color_fifo.py` inspects all six NCLIP-positive paths with packet linking, decoding MIPS `SWC2` registers and signed address displacements. It deliberately excludes the conditional branch's delay slot from *fallthrough-only* evidence and checks packet-register identity, complete FIFO triplet and family-specific color word positions.

Local EXE results: **one complete, offset-matching RGB0/RGB1/RGB2 triplet in one of two GT3 paths**, and **none** in the other four triangle-family paths. This does not establish the source of color fields in the remaining paths: they can be filled by other routines before polygon projection.

No UV/CLUT/Texture Page values and no original GP0 opcode byte have been recovered. The triangle identities remain structurally supported candidates, not confirmed original opcode families.

## Reproduction and verification

```sh
python3 tools/audit_gp0_color_fifo.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The full staged host CMake project was built with C++20 and **35/35 CTest suites passed**, including six new Python tests in `tests/test_gp0_color_fifo.py`. The tests cover register/offset decoding, a full GT3 RGB triplet, different base CPU register, MIPS branch delay, invalid scan bounds and an empty input. These tests prove the static audit contract, not PlayStation GPU rendering or GTE arithmetic fidelity.

The next reverse-engineering step is to trace original GPU packet buffer initialization / loading to determine actual GP0 command modes and the provenance of UV, CLUT and texture page. GitHub Actions and a playable Nintendo Switch build remain unverified.
