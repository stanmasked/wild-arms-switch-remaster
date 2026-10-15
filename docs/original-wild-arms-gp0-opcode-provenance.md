# Original Wild Arms GP0 command-word provenance: partial static trace

## Method and private data

Using the user's locally extracted original `WILDARMS.EXE` (PS-X executable load address `0x80011420`), extended the previously verified NCLIP-positive OT packet auditor. Only derived instruction addresses, CPU register numbers and diagnostics are shared. **No original game binary or assets were uploaded.**

The PS1 GPU packet begins with a one-word linked-list tag at packet offset +0. The first GP0 command/color word begins at **packet offset +4**, and its **opcode is the byte at offset +7**, because the PS1 instruction encoding stores the GP0 command in the high byte.

The new `tools/audit_gp0_opcode_provenance.py` inspects six polygon-building code regions for MIPS `SW`, `SH` and `SB` writes to those positions, and detects nearby `LBU rN,7(packet)` followed by `SB rN,7(packet)`. It distinguishes stores before `BLEZ`, the branch-delay slot, and the fallthrough path. This is **static provenance evidence, not a byte-value decoder**.

## New confirmed evidence

| NCLIP | Layout | Relevant write | Meaning |
|---|---|---|---|
| `0x80066F64` | GT3 candidate | `SB r1,7(r11)` at `0x80066FC8`, after `LBU r1,7(r11)` at `0x80066FAC` | Rewrites the previously loaded opcode byte |
| `0x800671F8` | FT3 candidate | `SW r12,4(r11)` at `0x8006720C`; `SB r1,7(r11)` at `0x80067210`, after `LBU r1,7(r11)` at `0x80067208` | Replaces the GP0 command/color word but restores its pre-existing opcode byte |

Both `FT3` writes occur **before** the nearby `BLEZ` at `0x8006721C`. The GT3 byte store occurs on the following fallthrough path. The other four audited paths contain no direct +4 word/+7 opcode-byte stores in the selected 24-instruction lookback and forward packet-link interval. This does **not** mean their opcodes are absent: they may be initialized when the packet buffer is created or reused.

The real EXE audit totals are:

- **1** direct first GP0 command-word store (`SW` at packet +4).
- **2** direct opcode-byte stores (`SB` at packet +7).
- **2** `LBU` to `SB` pairs consistent with opcode-byte preservation.

Importantly, **no actual byte values were derived**. Therefore F3/G3/FT3/GT3 remain **structural packet-type candidates**; opcode submodes (semi-transparency, raw texture, dithering-related behavior) remain unknown. The pair recognition is local static dataflow and does not prove the register was never changed by control-flow outside the scan window.

## Reproduction and tests

```sh
python3 tools/audit_gp0_opcode_provenance.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

`tests/test_gp0_opcode_provenance.py` contains **6** regression tests for decoder width/sign, distinguishing LBU from stored opcode values, correct packet register, save/restore, and branch-delay-slot classification.

**Local verified result: full CMake/C++20 build succeeded and 34/34 CTest suites passed**, including the newly registered `wa_original_gp0_opcode_provenance`. The private original executable was inspected locally and not committed.

Next investigate the creation/initialization path of GPU packet buffers to recover where their first GP0 opcode bytes actually originate, along with UV/CLUT/texture-page fields. A live game trace and independently authenticated PS1 GTE register captures are still missing. GitHub Actions and native Nintendo Switch game execution were not verified.
