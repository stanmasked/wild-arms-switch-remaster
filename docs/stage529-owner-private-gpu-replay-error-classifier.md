# Stage529 — independently classify real developer-logo GPU replay disagreement

The Sony publisher intro Stage516 five-file SHA/CRC/RGB seal passed using a
real GUI-exported V2. The separately captured Media.Vision developer-logo
intro has a **different** property: the authentic detached GUI V2 equals
the entire pretrace 1MiB VRAM byte-for-byte, whereas the still-experimental
GP0(2C)/(64) model gives a nonmatching full image.

The first thing to establish is **what kind** of mismatch exists before
changing a GPU rasterizer. Adding a fixed UV or destination pixel shift
without evidence could make authentic parity worse.

## New ROM-free diagnostic tool

`tools/classify_private_gp0_frame_differences.py` accepts three distinct
caller-supplied immutable, exact-size (1024x512 u16le) VRAM images and an
explicit bounded ROI. It returns only statistical counts: modeled versus
observed colored/black mismatches, mismatched RGB555 channel magnitudes,
changed rows and coarse tiles. A fixed +/-2 pixel shift sweep is provided
only as a diagnostic heuristic. It is **not** a substitute for PS1 polygon
edge rules, or a trusted way of authenticating the original capture.

Strictly reject malformed/mutable inputs, wrong VRAM sizes and unknown
or out-of-bounds ROIs. No pixels, game identifiers, game-content hashes,
texture indices, private screenshots or original-GP0 words enter public
tests or GitHub. The real-game derived analysis and reproduction script
must remain owner-private in Google Drive.

## Narrow findings from the owner-only actual-frame comparison

The original real compiled PCSX-Redux Player Frame1 V2 **matches pretrace**.
The experimental full-frame reproduction differs from it at **10,564
16-bit VRAM words**. Classifying these mismatches shows:

- **1,503** model-zero versus authentic-nonzero words;
- **1,220** model-nonzero versus authentic-zero words;
- **7,841** nonzero words with incorrect RGB555 color.

The best of the bounded integer translation checks is the **unshifted**
model. A global one-pixel shift is not a verified repair. Detailed
source-derived statistics, exact private hashes, ROI and scripts are
archived owner-only and are deliberately not part of public CI.

## Pinned emulator source clarification

The pinned PCSX-Redux soft rasterizer `src/gpu/soft/polys.cc` has a
fast path whose condition includes
`Shading == GPU::Shading::Flat || !m_ditherMode`.
Consequently, detecting E1 dithering bit9 in an actual flat-shaded
textured GP0(2C) packet **does not alone prove that dithering caused the
non-parity**. The experimental rectangular UV replay in Stage528 is
still correctly fail-closed on unmodeled dither-bearing configurations,
but neither a one-flag guess nor this statistical classifier completes
polygon rasterization.

Next: compare PCSX-Redux's two-triangle edge walkers, half-open pixel
coverage, affine UV seed with 0x8000 half-LSB bias, texture page updates
and actual packet order against the owner-private trace. Do not claim
Media.Vision full-frame parity or Surf Village until independent
frame-level evidence confirms it.
