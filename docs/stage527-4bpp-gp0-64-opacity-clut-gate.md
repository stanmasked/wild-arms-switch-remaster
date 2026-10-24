# Stage527 — opaque GP0(64) four-bit CLUT rectangles (ROM-free)

This patch extends the already-tested Stage524 *bounded* software replay
with **GP0(64), textured variable-size opaque rectangles using 4-bit indexed
textures**. It is stacked on Stage526's genuine original-game Sony intro
five-file proof but does **not** modify that proof or copy any original data.

## Verified command interpretation

An original, independently archived Wild Arms *developer-logo* GPU capture
uses two GP0(64) packets and two GP0(2C) textured quadrilaterals. The two
GP0(64) draws use an E1 draw mode with 4-bit texture depth; the Sony publisher
intro instead used 8-bit GP0(66). The latter is semi-transparent when the
resolved CLUT texel's STP bit is set. **GP0(64) is opaque regardless of its
resolved texel's STP bit.** Both commands reject a transparent RGB555 zero
texel, not blindly palette *index* zero.

In supported 4-bit mode, a little-endian 16-bit VRAM word contains four
4-bit palette indexes. The two 8-bit UV components locate texture samples
relative to the E1 texture page, wrapping within their 256x256 texture
coordinate space. The high 16 bits of the primitive UV word select the
16-entry CLUT on a 16-halfword X grid. Color modulation uses the original
Stage524 channel formula, and the RGB555 high STP bit is carried to VRAM.

Only an **explicit** complete E1–E6 state and supported ABR1, no texture
window/offset/mask or flips is admitted. Non-wrapping target geometry,
draw-area clipping, CLUT/source bounds and no destination overlap with
the source texture/CLUT are mandatory. Other states/unknown packets fail.

The existing `replay_bounded_8bpp_intro` name remains a compatibility
entry point for previously sealed Sony intro evidence; it now selects the
proper supported texture depth based on the GP0 opcode. The renderer's
returned synthetic-only schema reports both GP0(66) and GP0(64) counters.

## Synthetic regression coverage

`tests/test_gp0_64_4bpp_stage527.py` tests four independently selected
palette nibbles, opaque STP handling, RGB-zero transparency, palette index
zero holding a nonzero color, modulation and saturation, nonzero CLUT X,
draw clipping without UV reindexing, wrong texture depth, unsupported
mask/texture-window/offset, texture aliasing, malformed rectangles,
zero-width no-op and exact GP0 E1 mode transitions between 8bpp and 4bpp.

The earlier Stage525 future-scene negative regressions are updated:
GP0(2C) **still fails** and GP0(64) in the wrong 8bpp state **still fails**.
No original GPU words, private game VRAM, CLUT contents or source hashes
are part of these synthetic tests or public CI.

## Explicit remaining limits

This PR does **not** rasterize GP0(2C) four-vertex textured polygons. Full
replay and 1MiB parity for the developer-logo frame have *not* been proven;
there are two still-unmodeled quadrilaterals in that original frame. Do not
skip them just because other memory regions happen to match a saved frame.

The already completed, owner-private Stage516 real GUI V2 five-file strict
seal remains valid **only for the Sony intro**. Surf Village gameplay,
camera, foreground and field geometry are still unverified. Any newly
captured original bytes must remain owner-only in Google Drive.
