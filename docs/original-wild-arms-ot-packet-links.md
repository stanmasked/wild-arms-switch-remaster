# Original Wild Arms: NCLIP-positive GPU packets linked into Ordering Table

## Local original EXE evidence

Audited the user's local extracted PS-X EXE, loaded at `0x80011420`, without uploading its bytes. Of 8 GTE NCLIP sites, six contain `NCLIP → MFC2 MAC0 → BLEZ`. Each of those six fallthrough intervals writes SXY0/SXY1/SXY2 with SWC2 and contains the following packet-link pattern:

- `AVSZ3` computes an ordering depth; surrounding CPU instructions derive an OT element address.
- `LW` loads the previous OT head.
- `LUI 0x00ff; ORI 0xffff` constructs `0x00ffffff`, and `AND` masks the packet's low 24-bit address.
- Another `LUI` supplies a packet command-word count in the high byte; `OR` merges it into the header.
- `SW` writes the tagged header to the packet, then `SW` writes the packet address into the OT slot.

| NCLIP | AVSZ3 | Packet header store | OT head store | Length byte |
|---|---|---|---|---:|
| `0x80066E2C` | `0x80066E58` | `0x80066E90` | `0x80066E94` | 9 |
| `0x80066F64` | `0x80066FD8` | `0x80067010` | `0x80067014` | 9 |
| `0x800670D8` | `0x80067104` | `0x8006713C` | `0x80067140` | 7 |
| `0x800671F8` | `0x80067238` | `0x8006728C` | `0x80067290` | 7 |
| `0x800673B8` | `0x800673E4` | `0x8006741C` | `0x80067420` | 4 |
| `0x8006749C` | `0x800674C8` | `0x80067500` | `0x80067504` | 6 |

The length byte specifies GPU packet **command words following the tag**, not a confirmed primitive type. Identifying polygon modes will require checking GP0 opcode, UV and color fields in the packet-writing code.

## Reproducible audit

`tools/audit_nclip_ot_packets.py` accepts a locally extracted PS-X EXE and emits derived addresses, length bytes and per-site summaries, without copying original instructions or graphics into the repository:

```sh
python3 tools/audit_nclip_ot_packets.py /private/path/WILDARMS.EXE
```

It checks actual MIPS register dependencies between the loaded OT head, mask construction, tag construction and both stores, scanning only after the BLEZ delay slot and before the forward branch destination.

The local original-game scan reports **8 NCLIP, 6 MAC0/BLEZ chains, 6 SXY triplets, 6 packet-link candidates**. The five synthetic tests in `tests/test_nclip_ot_packets.py` cover four observed packet lengths, correct address linkage, malformed masks and backward-branch exclusion.

A new local CMake/GCC build of the staged project and full CTest run passed **32/32 suites**.

## Limitations

These are static *instruction-pattern candidates*, not proof that every path is reached during gameplay; branch interactions and DMA/OT submission have not yet been runtime traced. This audit does not prove GTE's arithmetic bit accuracy. There is no completed native Nintendo Switch Wild Arms binary, and GitHub Actions CI was not independently checked for these changes.
