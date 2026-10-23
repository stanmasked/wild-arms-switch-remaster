# Stage510 — exact Player Frame-1 PNG witness: no ambiguous visual transforms

This is a **synthetic-only** follow-up to [Stage509 issue #138](https://github.com/stanmasked/wild-arms-switch-remaster/issues/138) and the Stage456 verifier. The public code does not load original game media.

## Finding

`decode_private_opaque_rgb_png.py` already validates PNG framing/CRC, bounded decompression, full opacity, exact ROI dimensions and decoded RGB bytes. However, it previously allowed PNG ancillary metadata which changes how an image is presented, as well as APNG animation chunks. An operator could therefore supply an image whose decoded raw bytes equal a Frame-1 VRAM crop while the displayed/presented result is color-managed or animated differently.

Stage510 deliberately **fails closed** for color/gamma/HDR/background/EXIF metadata (`gAMA`, `cHRM`, `iCCP`, `sRGB`, `cICP`, `mDCv`, `cLLi`, `sBIT`, `eXIf`, `bKGD`) and APNG (`acTL`, `fcTL`, `fdAT`). Benign non-pixel `tEXt` metadata remains acceptable. The decoder still supports profile-free RGB or fully opaque RGBA, 8-bit non-interlaced PNGs with standard filters.

This constraint is intentionally conservative. A normal screenshot carrying an sRGB tag may still contain valid image bytes, but it cannot satisfy this *unambiguous strict visual witness* gate unchanged. Keep the original private screenshot; prefer a new direct, unscaled profile-free screenshot from the actual Player for the accepted witness. If metadata is losslessly stripped for diagnosis, preserve the original and separately record the derivation; do **not** describe such a derivative as a fresh UI capture.

## Owner-local capture and archive gate

1. Use the exact pinned patched PCSX-Redux build and native GPUDUMP. Record the executable provenance **privately**.
2. In the actual GPU Dump Player UI, rewind, step once to **Frame 1**, and use **Export Step 1 private VRAM...** to produce the V2 VRAM container.
3. Capture the visible Player preview using a trusted owner-local lossless, unscaled, non-color-transformed PNG ROI; record actual VRAM-relative `x/y/width/height`. Do not synthesize this PNG from exported VRAM: that would only test our own conversion.
4. Supply the private native GPUDUMP, imported prepacket VRAM, Frame-1 GP0 JSONL, GUI-exported V2 container, and screenshot to `tools/verify_private_gpudump_player_step1_dump_hash.py` with explicit ROI dimensions and the default strict RGB comparison. Optionally require a visibly changed ROI.
5. Keep raw files under `02_Raw_Traces_and_Captures/Stage509_Player_Frame1_RGB_Verification`, independent file manifest/checksums under `00_Manifest_and_SHA256`, and reports under `03_Aggregate_Reports` in the private Google Drive project archive. Recheck hashes on the downloaded archived copies before labeling the evidence durable.
6. Public GitHub should contain only a sanitized verification status and public CI identifiers. Never commit private captures, original game bytes, raw logs, private hashes, or original extracted textures.

## Evidence limitation

Matching RGB raw bytes show the provided PNG and detached VRAM agree under the exact pinned RGB555-to-RGB convention. This **does not** cryptographically attest screenshot provenance, identify the underlying gameplay scene, independently validate the GPU rasterizer, or prove Surf Village is rendered correctly. The strict gate remains pending until real privately archived same-frame materials have been checked.

## ROM-free regressions

`tests/test_decode_private_opaque_rgb_png_metadata.py` covers clean RGB/RGBA and benign metadata controls; rejects each listed color/animation ancillary type (including before/after IDAT); confirms the same policy for RGBA and enforces chunk CRC integrity. Existing checks for transparency, dimensions and pixel equality remain in place.


## Stage512 pinned Player UI capture geometry (source audit)

Pinned upstream `src/gui/widgets/gpudump.cc` calls `updateTexture()` before
`ImGui::Image`. The texture is 1024x512 RGBA, with nearest-neighbor scaling.
The GUI has two independent view controls:

- `Display area only` defaults to **on**, and clips using current GP1(05)
  VRAM start and GP1(08) mode. The displayed image is not the whole VRAM.
  If using this mode, record the GPU display rectangle origin **in VRAM
  coordinates** as well as the actual PNG crop. A screenshot's top-left at
  pixel 0 is not necessarily VRAM x=0, y=0.
- `Zoom` defaults to 1.0x but is user-adjustable from 0.5x to 4.0x.
  Select 1.0x and verify the final **physical-pixel** capture is one-to-one,
  without OS display scaling, window resizing, or screenshot interpolation.

For the simplest full-VRAM capture, disable `Display area only`, set `Zoom`
to 1.0x, and capture a completely visible, unobscured source-aligned ROI from
the actual Player preview after it displays Frame 1. Log the ROI's original
VRAM x/y/width/height and the screenshot extraction method privately.
Never assume mouse/window/DPI coordinates equal VRAM coordinates without
independent confirmation. No accepted ROI may cross a VRAM row boundary.

The captured PNG must not be generated from the separately exported V2
container: that is a tautological consistency check, not independent
observation of Player's displayed texture. Preserve both the untouched
UI screenshot and any diagnostic conversions separately and identify the
conversion lineage in the private manifest. Even strict exact RGB equality
cannot attest the screenshot's UI provenance or GPU rasterization correctness.


## Stage513–514 — synthetic ROI offsets and native GP1 display-window gate

Stage513 regression exercises a synthetic three-by-two ROI at VRAM (211,37),
with distinct RGB555 colors across two 1024-word VRAM rows. The exact
same-file PNG comparison must pass only for its true VRAM origin and
orientation; a one-pixel x/y offset, swapped row or changed width must fail.

For a capture of the **entire** Display-area-only preview, the Stage514
V2 verifier now supports the optional `--require-native-display-window`.
When enabled, the verifier derives the GP1(05) display start and GP1(08)
display mode from the bound native dump's *pretrace* control records and
requires the provided x/y/width/height to equal that exact rectangle.
Unobserved or repeated display controls must fail closed. The comparison
assumes the supported first-step trace does not change the display geometry
before its first VSync. This gate is deliberately **not** the default:
for a smaller manually cropped portion of a full-VRAM screenshot it would
incorrectly require the crop to cover the whole display window.

For example, append `--require-native-display-window` to the Stage456
private verifier invocation **only** when the PNG is a native-resolution,
unscaled complete GP1 display rectangle and the privately recorded
coordinates match the GP1 start. Keep the original screenshot and
coordinate provenance in private Drive. Matching pixels cannot on its
own authenticate the screenshot's actual UI origin.
