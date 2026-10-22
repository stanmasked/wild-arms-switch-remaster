# Stage447 — import real PCSX-Redux native GPU Dump Recorder frames privately

## Source-confirmed built-in capture (no custom GPU hook needed)

Unlike the ordinary GPU Logger, PCSX-Redux **has a native GPU Dump
Recorder / Player** in upstream source at fixed revision:

`de4a33e9a69abec4f567ae33567537f867dc2bba`

- GUI menu: **Debug > GPU > Show GPU dump recorder / player**.
  Recorder UI: **Start recording...**, file-save dialog, then
  **Waiting for the next vsync...**, **Recording, N frames**, and
  **Stop recording**.
- Capture arms at the next v-sync where the GP0 parser is idle, avoiding
  starting partway through a GPU command.
- Its native file begins with **PSXGPUDUMPv1r1** and contains typed
  GP0/GP1 records, game metadata, v-sync cycle stamps and a TraceBegin
  marker. Before TraceBegin the recorder writes **GPU reset, a complete
  1024×512×16bpp VRAM snapshot and the GP0(E1–E6)/GP1 restore state**.
- The recorder records both direct CPU and DMA GPU writes via the GPU
  data-entry path. The built-in **Player** can load, rewind and step
  captures without advancing the real game.

Upstream reference implementation:
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.h
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/core/gpudump.cc
https://github.com/grumpycoders/pcsx-redux/blob/de4a33e9a69abec4f567ae33567537f867dc2bba/src/gui/widgets/gpudump.cc

The companion Stage446 raw GP0-u32le packager alone **cannot**
parse this native container. Stage447 now bridges the native
format directly to the project's private analysis tools.

## Implementation and first-frame acceptance

`tools/import_private_pcsx_native_gpudump.py`:

1. Parses the 16-byte magic and bounded little-endian typed
   packets, including each 32-bit record header with an 8-bit
   packet type and a 24-bit **word count**. Rejects all truncated,
   unknown and oversized packet records, including corrupt
   native VSync/TraceBegin records.
2. Requires the upstream **GPUVersion=2**, GP1 reset and one
   **262,147-word** GPU A0 transfer of the complete starting
   VRAM, anchored at X=0/Y=0 with 1024×512 dimensions.
3. Extracts **1,048,576 original VRAM bytes** from the full
   pretrace A0 block. This initial upload is **bootstrap state**,
   not historical traffic in the first game frame. It does not
   enter the live packet sequence or the Stage437 packet limit.
4. Requires exactly the ordered **E1,E2,E3,E4,E5,E6**
   GP0 restore environment before one TraceBegin marker.
   These six initial conditions are prepended to the modeled
   JSONL as explicit *restoration state*, not claimed to be
   original first-frame game commands.
5. Collects only GPU GP0 bytes **after TraceBegin and before
   the first native VSync**. No middle-of-a-packet imports or
   borrowing words from a later frame. Later VSync frames remain
   ignored because their correct initial VRAM would require
   real GPU rasterization/replay of all preceding frames.
6. Fails closed if any unmodeled live GP1, GPU readback, or
   unsupported source command is observed. This supported subset
   may therefore reject authentic dumps; such rejection is
   a clear indication of missing decoder support, not evidence
   that the original game is incorrect.
7. Passes the extracted first-frame GP0 wordstream to the
   Stage446 strict packetizer and validates its final
   Stage437-compatible JSONL. Writes **two private files**
   atomically and without clobber, with restrictive permissions:
   - `surf-first-frame.before.u16le.bin`
   - `surf-first-frame.gp0.jsonl`
8. Emits metadata only (hashes, frame count, packet counts,
   provenance caveats). **Native dump contents, private hashes,
   source CDSTG and rendered game pixels must never go to
   public CI or GitHub.**

The saved GPU dump format and its native recorder together
provide stronger structural provenance than a manually typed
packet list, but a file on disk does not cryptographically attest
the executable version, original game revision, map identity or
camera position. Every claimed original frame must still be
compared with the actual screenshot and disc identity.

## Owner-local capture workflow

Once PCSX-Redux at a build containing the native recorder and the
owner's original Wild Arms disc are available **on the same private
machine**:

1. Boot the original game and navigate to **Surf Village**.
2. Open **Debug > GPU > Show GPU dump recorder / player**.
   Start recording while the desired village scene is visible.
   The capture begins at the next idle GP0 / v-sync boundary.
3. After one or more game frames, select **Stop recording**.
   Save the native dump somewhere private **outside any public
   repository**, e.g. `/private/WildArms/gpu/surf.gpudump`.
4. Use the native GPU Dump **Player** to confirm the frame contents
   visually; do not substitute a different frame or unrelated
   paused screenshot/VRAM.
5. Run:

```sh
python tools/import_private_pcsx_native_gpudump.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/surf-first-frame.before.u16le.bin \
  /private/WildArms/gpu/surf-first-frame.gp0.jsonl \
  --frame 0 \
  > /private/WildArms/gpu/stage447-private-import-report.json

python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/surf-first-frame.before.u16le.bin \
  /private/WildArms/gpu/surf-first-frame.gp0.jsonl \
  --map-index 2 \
  > /private/WildArms/gpu/stage447-private-clut-analysis.json
```

The paths are examples. The tool does not download, mount or
publish the original 637MB Wild Arms BIN, nor does it execute
PCSX-Redux on behalf of the owner in this environment.

If an authentic dump contains GP0 commands unsupported by
Stage437–446 (for instance a framebuffer fill, line, or GPU VRAM
read), the importer **rejects it** rather than claiming a
complete supported replay. Real game reconstruction still needs
an expanded GPU model for those cases. An independently rendered
PS1 screen crop from Stages432–434 remains the final visual
comparison target, not merely a raw wordstream match.

## Synthetic CI

`tests/test_import_private_pcsx_native_gpudump.py` uses only
fabricated 1 MiB VRAM, artificial GP0 words and **22 ROM-free tests**.
Checks cover full native v1r1 framing, header/version/typed record
validation, exact extraction of pretrace 1024×512 A0 snapshot,
separate initialization versus live first-frame traffic,
multiple GP0 transport records, v-sync selection, unsupported live
GP1/readback rejection, truncated packet failures, no-clobber
publication, symlink protection and report privacy.

**Passing CI is not an authentic original-game dump.**
The genuinely useful next gate is performing a private capture
with the owner's original disc and comparing its typed native
GPU Dump Player frame with source-grounded Surf Village graphics.
