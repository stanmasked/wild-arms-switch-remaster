# Stage433 — private reference-patch evidence from actual PS1 screenshots

## Objective

Stage432 can save a **private** PCSX-Redux witness bundle containing
two identical paused VRAM reads, a PNG screenshot, a CD-info response
and a SHA-256 manifest. Stage431 can compare rows found in two distinct
VRAM dumps. Neither stage reconstructs source tile placement.

Stage433 adds the missing controlled **screen-space patch** workflow
that future original-style restoration candidates can be evaluated
against without accidentally converting a texture atlas into a
supposed authentic game frame.

The first intended landmark is a Surf Village **roof or well**,
selected manually by the game owner/researcher from an actual screen
capture. This stage provides a rigorous comparison instrument only;
no screenshot from an original gameplay run has been submitted to it,
and no map-tile-to-atlas-to-CLUT assignment is claimed.

## Exactly what is checked

- The source Stage432 screenshot, the original VRAM and the CD-info
  JSON must **all** pass the Stage432 SHA-256 manifest verifier before
  the reference image can be loaded.
- The operator explicitly specifies screen-space `x, y, width,
  height`. The ROI must fit inside the screenshot, be a positive
  integer rectangle and contain at most 1,048,576 pixels.
- A private reference PNG is cropped from the original screenshot,
  **without** resizing, denoising, sharpening, recoloring or inventing
  missing details. No AI image generator is involved.
- Optionally, supply a *different PNG that is already a rendered scene
  patch* at exactly the same width and height as the reference ROI.
  **Do not supply Stage426 atlas contact sheets as the candidate.**
  The candidate must come from a scene renderer with matching frame
  coordinates, camera and HUD conditions.
- The input PNGs must be fully opaque after conversion to RGBA;
  transparent candidates are rejected instead of implicitly using
  an unknown compositing background.
- When the candidate is supplied, compare raw RGB bytes at exactly
  matching pixel positions; **never** resample, auto-align, stretch,
  color-grade or ignore an alpha difference.
- Report exact matching pixels; pixels exceeding a configurable
  per-channel absolute error threshold; discrepancy bounding box,
  maximum channel error, mean absolute channel error, and RGB RMSE.
- An optional three-panel private PNG contains: reference ROI,
  same-size candidate and absolute RGB difference (same dimensions
  for each, separated only by narrow gutters).
- An accompanying owner-private JSON includes the witness's
  screen/VRAM/CD-info SHA-256 values, screenshot ROI, reference and
  candidate pixel hashes, metrics and explicit non-proof flags.
- Outputs are never overwritten and are only written after all
  decoding, geometry, provenance and comparison checks succeed.

## Reproducible LOCAL workflow

Have one actual private Stage432 capture called `surf_a` in
`/private/WildArms/surf-frame-witness/`. Create a second private
output directory outside the public repository:

```sh
python -m pip install Pillow
mkdir -p /private/WildArms/surf-roof-study

# First preserve a small reference ROI selected from the original screen.
python tools/audit_private_surf_reference_patch.py \
  /private/WildArms/surf-frame-witness surf_a \
  /private/WildArms/surf-roof-study roof_reference_v1 \
  --x 40 --y 50 --width 64 --height 48
```

The coordinates and dimensions above are **synthetic examples**;
they are NOT verified coordinates for any Surf Village roof.

When an independently rendered, source-verified, already registered
64×48 patch exists locally, run the optional comparison:

```sh
python tools/audit_private_surf_reference_patch.py \
  /private/WildArms/surf-frame-witness surf_a \
  /private/WildArms/surf-roof-study roof_comparison_v1 \
  --x 40 --y 50 --width 64 --height 48 \
  --candidate-png /private/WildArms/renderer/roof_patch_64x48.png \
  --threshold 0
```

Results, all owner-private:

- `roof_reference_v1.reference.png` and
  `roof_reference_v1.evidence.json` (reference only);
- `roof_comparison_v1.reference.png`,
  `roof_comparison_v1.comparison.png`, and
  `roof_comparison_v1.evidence.json` (comparison).

**Never commit** either original gameplay screenshot, cropped
reference, atlas art, candidate images, VRAM bytes, disc information
or derived evidence JSON/PNG to public GitHub/Actions. Use the
user-private disk and an owner-private transfer if necessary.

## Interpretation and acceptance gates

A numerical comparison is **not** an automatic visual restoration
certificate. An exact RGB match at a small ROI does not prove
the screenshot's original game/map identity, the source LZSS stream,
PS1 texture page, draw-time GP0 CLUT, alpha/STP, geometry or ability
to move the camera without artifacts.

For a trustworthy first Surf Village landmark:

1. A human confirms the private captured screen really depicts
   Surf Village on the specific original game revision, and records
   camera/scene state. Source labels and disc-info bytes alone are
   not independent authentication.
2. Original texture upload/draw commands and CLUT usage are tied to
   the source tiles in that landmark. Stage428 requires independent
   GP0 instrumentation; no public PCSX-Redux REST endpoint for
   complete GP0 trace export is assumed.
3. A correctly positioned micro-patch is rendered under the
   equivalent video mode, camera and pixel coordinate convention.
4. Only then should numeric pixel differences be interpreted as
   restoration fidelity, and further frames/animation/transparency
   be evaluated. A static screenshot is not a complete game scene.
5. A validated owner-private patch can be imported into the Switch
   field renderer without publishing commercial artwork.

## Tests

`tests/test_audit_private_surf_reference_patch.py` uses only synthetic
byte buffers for the core metrics. Optional locally generated PNGs
test integration with the Stage432 capture manifest and screenshot
provenance if Pillow is available; those tests may be skipped if
Pillow is absent. No original game assets are required.

This PR is the next step toward source-grounded original-style HD
restoration, **not** an AI-generated roof, a recovered complete
Surf Village scene or a real emulator GPU capture.
