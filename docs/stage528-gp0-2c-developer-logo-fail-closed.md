# Stage528 — bounded GP0(2C) 4bpp quads and authentic GUI discrepancy gate

The independently stored *Wild Arms (USA)* developer-logo capture contains
two GP0(2C) textured four-vertex polygons and two GP0(64) sprites. An exact
real-game first-frame VRAM comparison was previously left **OPEN**, rather
than pretending arbitrary polygon commands could be ignored.

## ROM-free code

`tools/replay_private_gp0_quad_2c.py` adds a narrow **axis-aligned,
one-texture-pixel-per-screen-pixel** GP0(2C) mode. Each complete polygon
packet must have exactly nine u32 words: opaque colored command, four
signed XY vertices and four corresponding UV words. The first UV contains
the 4bpp CLUT, while the second UV supplies its **own texture page**,
distinct from E1 for later GP0(64) rectangles. All source/destination
coordinates and 16-entry CLUT are VRAM bounded and non-overlapping.

Only a canonical rectangular quad with correct matching UV corners,
width/height at most 256 and explicit E1–E6 drawing area/mask/window/
offset conditions is accepted. The command does **not** purport to
implement arbitrary triangle edge coverage or perspective interpolation.
The 4-bit nibble lookup, RGB555 tint modulation and bit15 STP retention
are tested against wholly synthetic pixels; opaque 2C never invokes
transparent-blend ABE. Unknown states/geometry fail closed.

The existing `replay_bounded_8bpp_intro` entry point gains a guarded
case for this packet while preserving both GP0(64) 4bpp and GP0(66) 8bpp.
New ROM-free regressions verify UV, palette, tint, bounds, feedback
rejection, fail-closed negative cases and preservation of the Sony intro.

## CRITICAL: independently verified real original trace discrepancy

The owner-private Stage517 Media.Vision developer-logo capture's saved
detached `frame1-vram.u16le.bin` is **identical** to its original
pretrace/rewind 1MiB VRAM, despite live GP0(2C)/(64) packets. Replaying
all 19 native first-frame packets under the *experimental*
one-to-one textured-rectangle assumption produces nonzero pixel
differences. This is **not** a full-frame GPU parity proof.

To rule out simply mistimed Stage517 postframe evidence, a new session
with the successfully CI-built pinned PCSX-Redux opened the *original*
developer-logo native GPUDUMP in the **actual GPU Dump Player**, used the
real GUI's Frame 1 **Export Step 1 private VRAM...** button by ImGui
keyboard focus, and produced a new C++ native V2. The exact GUI-produced
1,048,640-byte V2 passed header/frame/native-hash/CRC tests and its
1MiB VRAM **again equaled** both the original Stage517 postframe and
native rewind, with zero changed u16 words. The frozen image in the GUI
was a developer-logo picture.

Thus the unchanged Player VRAM is **confirmed**, and the experimental
polygon/sprite replay differs from it. Do **not** claim that Stage528
matches authentic developer-logo memory or blame earlier capture timing.

A further owner-private audit found that both original GP0(2C) polygons
execute with the **E1 polygon-dither bit (bit9) enabled**. The Stage528
quad approximation does not model GPU dither/triangle edge coverage;
the integrated public renderer therefore **rejects E1 bit9** for 2C
and synthetic CI asserts this refusal. This is an explicit runtime
blocker, not evidence of a successful full-game polygon rasterizer.
The difference may arise from PS1 rasterization conventions (triangle
edges, UV interpolation and framebuffer rules) or replay modeling; its
cause is not established. Keep this original-output negative witness
in private Drive as a regression target for subsequent work.

This result does **not** invalidate the separately proven Sony intro
Stage516 five-input strict seal and independent real GUI V2, or
automatically establish Surf Village rendering. Original captures, V2,
screenshots and all game-derived private SHA-256s remain owner-only.
