# Stage432 — owner-private paused VRAM + screen + disc witness

## Purpose

Stages 426–431 recovered 112 plausible palette-row candidates from
original Surf Village map #2, created candidate-to-VRAM/GP0 matching
tools, and added repeatable paused VRAM captures. None of this
establishes which actual game scene is visible at capture time.

Stage432 **preserves the screenshot and current CD information from the
same local PCSX-Redux pause window as two byte-identical VRAM reads**.
This provides a visual artifact for subsequent HUMAN verification and a
local fingerprint of the emulator's disc-info response. The tool does
not identify the game or map automatically.

PCSX-Redux REST documentation independently lists the following GET
endpoints:

- `/api/v1/execution-flow` — JSON with `running` flag;
- `/api/v1/gpu/vram/raw` — full VRAM;
- `/api/v1/screen/still` — PNG screenshot;
- `/api/v1/cd/info` — information about loaded CD.

Reference: https://pcsx-redux.consoledev.net/web_server/

**This API does NOT document a GP0 packet stream exporter.** The GPU
Logger can inspect primitives and replay after a VSync, but it may
only retain part of a game-rendered frame:
https://pcsx-redux.consoledev.net/Debugging/gpu-logger/

Do not claim a Stage428 packet trace was captured by this tool.

## Owner-local capture

On the owner's computer: launch the real Wild Arms disc using
PCSX-Redux, navigate to Surf Village and pause a visible field
scene. Enable its web server only on a trusted, isolated host.
The PCSX-Redux web server may listen on all interfaces by default;
our read-only helper only uses 127.0.0.1 or [::1] but cannot change
the server's network exposure. Use a local firewall.

Create an output directory **outside public GitHub** and run:

```sh
mkdir -p /private/WildArms/surf-frame-witness

python tools/capture_private_pcsx_frame_witness.py \
    /private/WildArms/surf-frame-witness \
    --basename surf_a \
    --label 'Surf Village, paused, local evidence'

python tools/capture_private_pcsx_frame_witness.py \
    /private/WildArms/surf-frame-witness \
    --basename surf_a --verify-only
```

Use the actual filesystem location of the user-owned disc and a
private output path valid on the local machine.

The HTTP **GET-only sequence** is:
1. GET execution-flow: require `running=false`.
2. GET full VRAM #1, exactly 1,048,576 bytes.
3. GET execution-flow: require `running=false`.
4. GET screen/still: bounded valid PNG with IHDR, IDAT, IEND and CRCs.
5. GET cd/info: bounded nonempty JSON object, duplicate keys rejected.
6. GET execution-flow: require `running=false`.
7. GET full VRAM #2: must exactly match the first read.
8. GET execution-flow: require `running=false`.
9. Publish the four private files **only if every check passed**.

An error or VRAM discrepancy leaves no newly published files.
The capture never issues pause, resume, reset, memory-write or disc
patch POST commands. It rejects remote hosts, redirects, bad
response status, oversized files and unsafe basenames.

## Four local output files

- `surf_a.u16le.bin`: actual 1 MiB raw VRAM bytes from the paused
  emulator (input for Stages427–428 and Stage431).
- `surf_a.screen.png`: original screenshot returned by PCSX-Redux.
  This is **owner-private copyrighted gameplay content**; never
  commit to GitHub or upload to public CI artifacts.
- `surf_a.cdinfo.json`: private original response from `cd/info`;
  inspect locally to check game identity. It is not authenticated,
  and the helper deliberately makes no claim that this disc is
  Wild Arms or the right revision.
- `surf_a.capture.json`: SHA-256, byte lengths for the three binary
  sources, PNG dimensions, operator label, four paused observations,
  two identical raw reads, and explicit provenance uncertainty.

All files are 0600 where POSIX permissions are available; publication
is no-clobber with rollback on failure. `--verify-only` checks every
file hash, length, file name and PNG structure and rejects corrupt
metadata. No screenshot/color/VRAM bytes are printed to the terminal.

## Use with Stage431 pair comparator

Stage432 also updates `read_verified_paused_capture` from Stage431:
it recognizes the original Stage430 double-read manifest **or** this
Stage432 witness, but for Stage432 it requires `verify_private_frame_witness`
to validate the PNG and CD-info sidecars before doing comparisons.
A fabricated/modified metadata claim cannot skip sidecar verification.

Capture a **second** independently paused view as `surf_b` using the
same operator label; compare on the owner's local machine:

```sh
python tools/audit_surf_paused_vram_pair.py \
    /private/WildArms/CDSTG.BIN \
    /private/WildArms/surf-frame-witness \
    surf_a surf_b \
    --map-index 2 > /private/WildArms/private-stage432-pair.json
```

Important: the screenshot is not used as automatic proof that Surf
Village map #2 is visible. An independent human must verify the
scene and, preferably, compare a reference screenshot to the original
PS1 frame under repeatable camera conditions.

## Limits and next proof gates

The screenshots are captured while the API reports paused, but this
does **not** prove a globally atomic GPU/VRAM/image capture or any
particular original frame number. A zero screenshot/VRAM delta could
also be found in an unrelated scene. CD-info JSON can be spoofed or
lack identifying details. Full PNG decoding is not independently
performed here; only bounded file/chunk structure and CRC are checked.

No GP0 trace is acquired. Without actual original GPU packet timing
and texture-upload-to-stream association, **no 16-color row is yet
verified as the chosen PS1 Surf Village palette**.

This stage uses synthetic in-memory REST responses and generated PNGs
for public CI. It does not require the original disc, BIOS, derived
artwork, genuine screenshot or runtime VRAM. The first real frame
witness is a separate owner-private evidence gate.
