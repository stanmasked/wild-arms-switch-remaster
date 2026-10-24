# Stage534 — savestate byte drift localized to inactive CD-ROM FIFO storage

## Result

The Stage533 repeat runs had identical raw VRAM output but savestate files differed by two bytes. I parsed the PCSX-Redux v5 protobuf envelope and audited all five neutral/LEFT/RIGHT/UP/DOWN after-state pairs. In every pair:

- The serialized savestate sizes matched.
- Exactly two bytes differed across the entire savestate.
- Both differences were in the field SaveState.CDRom.responseFifo0.payload[8:10].
- The saved queue reported payload_size = 1 and payload_index = 1.
- The active payload prefix (byte 0), response-FIFO metadata, guest memory, CPU state, GPU state, and all other serialized fields were byte-identical.

The two differing bytes therefore lie outside the active one-byte payload. This is a much narrower finding than a general savestate mismatch; it does not prove that every future state or all emulation subsystems are deterministic.

## Pinned upstream source explains why inactive tail bytes can survive

The audit used the exact PCSX-Redux commit pinned by Stage531: de4a33e9a69abec4f567ae33567537f867dc2bba.

- In [cdrom.h, QueueElement](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/cdrom.h#L180-L221), payload is a fixed 16-byte array. clear() resets flags, payloadSize and payloadIndex, but does not clear the payload array. readPayloadByte() returns a payload byte only when the current index is below payloadSize.
- In [sstate.h, CDQueuePayload and CDRom fields](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/sstate.h#L314-L390), the full fixed 16-byte payload is serialized and responseFifo0 is CDRom field 46.
- In [sstate.cc, the save-state mapping](https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/sstate.cc#L204-L208), that field maps directly to m_responseFifo[0].payload.

This source behavior explains how stale bytes beyond the active payload length can be preserved in the serialized state. The exact earlier operation that wrote those two particular tail bytes has not been traced, so the report does not claim to know their immediate writer.

## New reusable audit gate

tools/audit_pcsx_state_serialization_stage534.py validates the PCSX-Redux v5 protobuf envelope, locates the response FIFO payload and queue metadata, and classifies a difference only if every changed byte lies beyond the declared active payload prefix. It refuses malformed protobuf, mismatched sizes, active-payload differences, queue-metadata differences, unexpected queue schema, symlinks and hardlinked inputs.

Its output explicitly says that this is protobuf-byte classification, not gameplay or hardware-parity attestation. Tests use small synthetic protobuf messages only; no original disc data, savestates, VRAM or private hashes enter GitHub CI.

## Updated acceptance status

- **Stage533 directional response:** PASS under the pinned PCSX-Redux software GPU.
- **Repeatable rendered VRAM:** PASS for neutral and all four directional conditions.
- **Savestate binary identity:** not achieved, but the observed two-byte delta is localized to the inactive tail of the CD-ROM response FIFO payload.
- **Exact writer of the inactive tail bytes:** OPEN.
- **Internal field-map index, PS1 hardware parity, Nintendo Switch runtime parity and complete remake graphics parity:** still unverified.

Private state-pair hashes and full diff reports remain in the owner-only Drive evidence archive.
