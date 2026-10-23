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
