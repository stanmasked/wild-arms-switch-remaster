# Stage448 — private native PCSX-Redux GPU dump preflight

## What changed after finding the native recorder

At pinned PCSX-Redux commit
`de4a33e9a69abec4f567ae33567537f867dc2bba`,
the **GPU Dump Recorder / Player** can capture the emulator's
typed GP0/GP1 event stream and pre-recording VRAM. Stage447
provides a strict import for the first live frame, but real
captures may have GP1 display-control commands, GPU readbacks,
fills, lines or other operations the Stage437–447 modeled replay
does **not** support.

Those are not necessarily errors in the genuine capture. Rejecting
them without a **private structural diagnostic** would make
research difficult and could tempt operators to delete "offending"
commands and then falsely claim a complete GPU timeline.

Stage448 adds an owner-private preflight that **never changes the
GPU dump**, never publishes original words, and explicitly
distinguishes a syntactically complete native dump from the
narrow Stage447 modeled subset.

## Implementation

`tools/preflight_private_pcsx_native_gpudump.py` uses the
Stage447 bounded native packet-format parser and reports:

- SHA-256 and byte size of the exact native dump;
- total typed record counts grouped by GP0/GP1/VSync/GPUVersion,
  TraceBegin, readback, throwaway and metadata types;
- bootstrap counts **separately** from live frame counts
  (the enormous synthetic 1024×512 A0 initialization block is
  not the original game's first-frame packet traffic);
- bounded summaries for the first 12 VSync-delimited live
  frames (configurable up to 64), counting GPU port-0 **transport
  records and words**, GP1 transport events, readback/discard
  events and repeated TraceBegin markers;
- the number of completed native VSync intervals, even when
  the detailed summary list is truncated, and an explicit
  count of trailing events after the last VSync;
- an explicit accept/reject indicator from Stage447's **first
  frame import model**, plus its bounded structural error label.
  The label concerns only command support and stream geometry,
  *not* successful game-emulator execution or authentic scene
  identity.

**Important:** a native typed GP0 record is not necessarily a
whole GPU primitive or a whole A0 transfer. GP0 command bytes may
span several native records, and live GP1 may interleave with
unfinished GP0 commands. The diagnostics therefore do not
claim a per-primitive count or invent packet boundaries when
Stage447 cannot safely reconstruct them.

The tool produces metadata only and never includes the original
game ID string, CDSTG, graphics bytes, palette colors, VRAM
snapshot, GPU packet payload or rendered scene image. Even
hashes, numeric counters and reports must remain owner-private.

## Owner-local usage

When the owner has saved an original Wild Arms capture with
**Debug > GPU > Show GPU dump recorder / player** in PCSX-Redux:

```sh
python tools/preflight_private_pcsx_native_gpudump.py \
  /private/WildArms/gpu/surf.gpudump \
  --max-frame-summaries 12 \
  > /private/WildArms/gpu/stage448-private-preflight.json
```

If the preflight says `first_frame_import_accepted_by_stage447_subset:
true`, proceed with Stage447's importer into an original
prepacket VRAM file and ordered GP0 JSONL. If it says false,
**preserve the full original GPU dump** and identify the
unsupported GPU action before expanding the model. Do not
discard authentic packets solely to satisfy the test suite.

The PCSX-Redux native recorder can be opened locally and
visually played back; that is a separate verification surface.
A syntactically valid, possibly fabricated binary is **not**
proof of the original Wild Arms disc/map/camera revision or a
visible roof/well texture. Verified source-to-visible-frame
comparisons still depend on authentic PS1 captures, supported
GPU modeling and Stage432–434 screenshot crops.

## ROM-free synthetic tests

`tests/test_preflight_private_pcsx_native_gpudump.py` adds
**17 synthetic tests** covering bootstrap/live separation,
first-vsync frame boundaries, split GP0 transport records,
unsupported GP1/readback/throwaway and GP0 commands, repeated
TraceBegin, missing first frame, invalid binary framing,
sample truncation, private-file safety and absence of source
contents from summary metadata.

The source of the file format is
https://github.com/ps1dev/standards/blob/main/GPUDUMP.md
and the verified upstream recorder implementation is
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.cc.

The Stage448 code has not recorded or analyzed any actual
original-game native dump in this session; no actual Surf
Village artwork has been asserted restored.
