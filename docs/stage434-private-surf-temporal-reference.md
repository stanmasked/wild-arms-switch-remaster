# Stage434 — compare TWO original field-frame witnesses before judging Surf art

## Goal and why this stage exists

Stages426–431 recovered private candidate palette rows and developed
VRAM/memory checks. Stage432 captures an owner-private PS1 VRAM + original
screen + CD-info witness. Stage433 can crop a known screen rectangle and
compare an already-rendered (same-size) scene patch pixel for pixel.

One original screenshot cannot distinguish a misrendered roof from a
moving NPC, fountain animation, scrolling/particles or different
gameplay frame timing. **Stage434 checks the pixel-level temporal
consistency of one fixed ROI in TWO independently captured PS1
screenshots.**

The resulting mask marks only those pixels whose RGB values differ by
no more than a specified per-channel threshold in the two observations.
That is NOT an authenticated static map layer or a verified PS1 tile.

## Input privacy and contract

- Use two separate Stage432 owner-private, paused and byte-stable frame
  witness bundles, such as `surf_a` and `surf_b`, taken while observing
  the same scene/camera, in a private directory outside GitHub.
- Both must pass Stage432's integrity check on VRAM, screen PNG, and
  CD-info bytes. Snapshot names must differ. Image width/height must
  match exactly; the two raw `cdinfo.json` SHA-256 digests must match.
  These checks can prevent accidental mismatch but **do not prove**
  that either screenshot truly depicts the desired Wild Arms map.
- `x,y,width,height` denote exactly the SAME raw screen rectangle in
  both frames; they are manually selected and bounded by both screens.
  The tool does not search, move, scale, crop-to-fit, denoise or
  color-grade either frame.
- Candidate PNG is OPTIONAL and must be an independently generated,
  fully opaque **already-rendered in-scene patch** with exactly the ROI
  width and height. Stage426 raw 4bpp atlas sheets are NOT suitable
  candidates and must not be substituted.

## Output and metric semantics

Only on private local storage, the script writes:

- `<study>.first.png` — first exact original screen ROI;
- `<study>.second.png` — second exact original screen ROI;
- `<study>.temporal-mask.png` — white where the original pixels
  match within temporal tolerance, black where they differ;
- optionally `<study>.candidate.png` — the supplied same-size
  candidate reconstructed patch;
- `<study>.evidence.json` — SHA-256 reference identifiers,
  thresholds, ROI location, temporal counts, and optional candidate
  metric results (not original RGB data).

**The JSON is private evidence too**, even though it does not contain
a raw screenshot or palette. No original assets or derived images
enter public GitHub, Actions or release NROs.

With a candidate, the report always contains **two sets of metrics**:

1. **All-pixel** count/error metrics from Stage433, including every
   pixel of the first reference, regardless of temporal behavior.
2. **Temporally consistent-pixel only** metrics using the two-screen
   mask. The report explicitly states how many changing pixels were
   excluded from this secondary score. If zero pixels are consistent,
   the stable-only score is null, never a misleading zero error.

A zero-error consistent-pixel score **never overrides** the all-pixel
score and does not establish original GPU palette use, a correct
rendered field map or authentic tile positioning.

## Reproduction on the owner's computer

Use the real original Wild Arms in PCSX-Redux, capture two locally
verified Stage432 witnesses with a matched scene/camera and actual
recorded capture conditions; example commands:

```sh
# Existing private directory containing surf_a and surf_b captures.
mkdir -p /private/WildArms/surf-temporal-study
python -m pip install Pillow

python tools/audit_private_surf_temporal_roi.py \
  /private/WildArms/surf-frame-witness surf_a surf_b \
  /private/WildArms/surf-temporal-study roof_pair_v1 \
  --x 40 --y 50 --width 64 --height 48 \
  --temporal-tolerance 0

# ONLY if we have an independently rendered 64x48 on-screen patch:
python tools/audit_private_surf_temporal_roi.py \
  /private/WildArms/surf-frame-witness surf_a surf_b \
  /private/WildArms/surf-temporal-study roof_candidate_v1 \
  --x 40 --y 50 --width 64 --height 48 \
  --temporal-tolerance 0 --candidate-threshold 0 \
  --candidate-png /private/WildArms/renderer/roof_patch_64x48.png
```

Coordinates are **synthetic illustrative values**, not observed
Surf Village roof coordinates. These private commands cannot run
until actual original emulator witnesses exist on the owner's machine.

## Audit boundaries / next gate

- A matching pair of CD-info bytes is not a disc revision attestation.
- Screen SHA-256s being identical is flagged. Two identical screens
  may represent the same paused frame rather than independent
  observations; therefore unchanged pixels are never called static
  scenery by the tool.
- A pixel changing between frames might be animation, camera motion,
  different GPU state, image capture variance or incorrect scene
  selection. Do not blindly mask it and declare restoration complete.
- The two frame snapshots do NOT capture the 4bpp CLUT actually
  sampled during every GPU polygon draw. A complete GP0 packet trace
  or equivalent independently verified GPU instrumentation is still
  required to connect an original decoded atlas to tile geometry.
- This stage does not produce any new source-derived visual restoration
  until real original screenshots and a separately rendered candidate
  can be supplied privately.

## Synthetic CI

`tests/test_audit_private_surf_temporal_roi.py` tests the pure RGB
mask and scoring with synthetic in-memory pixels, as well as private
Stage432 capture/screenshot integration using entirely generated
images if Pillow is installed. The tests check same-size constraints,
thresholds, no-clobber behavior, SHA256 provenance, altered screens,
different CD fingerprints, and separate all-pixel/stable-only reports.

**Acceptance:** exact-head Disc analysis, Host Core and Matrix audits
are green; no real original screenshot is asserted or published.
