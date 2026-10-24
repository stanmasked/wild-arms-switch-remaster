# Stage532 — Surf Village controlled movement and private evidence seal

## Result: original-game movement observed

On 2026-10-24, the Stage531 owner-private checkpoint was restored with the exact pinned PCSX-Redux AppImage and the canonical Wild Arms (USA) BIN/CUE. The BIN size and SHA-256, CUE SHA-256, and AppImage SHA-256 matched the existing owner-private Stage531 manifest. The canonical BIN/CUE were reconstructed from the existing private Drive archive parts and remain the canonical source; they are **not duplicated** into the Stage532 evidence bundle.

The restored Rudy prologue was advanced through the default-name screen and into a no-dialogue village scene. A private PCSX-Redux GUI capture shows the playable scene with Rudy, NPCs, horses and buildings. The scene is visually consistent with Surf Village. The internal field-map index is **not independently confirmed**.

## Controlled A/B input experiment

Two independent software-GPU runs started from the exact same no-dialogue field savestate:

- Control: no directional input.
- Treatment: PCSX-Redux Lua pad override held **RIGHT** for 30 VSync frames, then returned to neutral.

The initial raw VRAM snapshots were byte-identical across the two runs. In the idle control, 872 framebuffer pixels changed during the sample interval, consistent with ongoing animation. Under RIGHT, 60,341 pixels changed. Phase correlation on the static upper-building ROI measured approximately **−27.0 horizontal pixels / +0.0 vertical pixels** of background displacement in the 320×240 framebuffer. Independently captured PCSX-Redux GUI before/after images visually show the corresponding camera-tracked movement. These measurements are private aggregate results; no original pixel data or private hashes are committed.

**Conclusion:** the original Wild Arms software-GPU run now demonstrates directional input affecting the visible Surf Village scene. This is not a claim of original PS1 hardware parity, Switch runtime integration, general GPU parity, or verified internal map index.

## Private archive and integrity boundary

The owner-private Stage532 archive retains:

- before/after PCSX-Redux savestates;
- before/after native 1 MiB VRAM snapshots;
- exact 320×240 framebuffer PNGs deterministically decoded from those VRAM snapshots;
- separately captured GUI screenshots from the same paused before/after run;
- the emulated input-state journal and runtime logs;
- a private manifest with source references, byte sizes and SHA-256 for every evidence file.

The GUI screenshots are supplemental visual evidence. Their on-screen origin is **not cryptographically attested**. The input journal is an operator-declared record of PCSX-Redux Lua pad overrides, not a physical-controller recording or trusted timing attestation.

The public tool tools/seal_private_rudy_route_stage532.py verifies the canonical BIN/CUE by external reference without copying either original into the evidence bundle. It binds the 320×240 framebuffer PNGs to the raw VRAM crop, checks state and VRAM differences, validates the CUE/track format, and seals all private evidence with a no-overwrite manifest. The verify operation requires the canonical source BIN/CUE to be supplied separately after the evidence ZIP is independently downloaded from Drive.

## Acceptance gates

- **Observed movement:** PASS in the owner-private PCSX-Redux run.
- **Frame-to-VRAM byte binding:** enforced by the private seal tool and synthetic tests.
- **Independent Drive archive readback:** must pass before this evidence bundle is considered durably archived.
- **Internal field-map index:** OPEN.
- **Full Surf Village graphics parity in the remake:** OPEN.
- **Nintendo Switch runtime / hardware parity:** OPEN.

Public GitHub CI uses synthetic fixtures only. Original BIN/CUE bytes, savestates, raw VRAM, GUI screenshots, input logs and private hashes remain in owner-only Google Drive.
