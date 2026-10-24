# Stage524 — bounded 8-bit indexed GP0(66) intro replay

The private real-game GPU dump for the *Wild Arms (USA)* introductory
Sony splash has exactly four GP0(66) rectangles, in addition to the bounded
GP0(02) quick fill and explicit GP0(E1–E6) GPU register updates.

**Critical corrected identification:** In the active GP0(E1) draw mode,
texture depth bits 7–8 encode **8 bpp**, not 15 bpp. Each 16-bit texture
word contains two 8-bit CLUT indexes; CLUT Y/X are taken from the sprite UV
word, whereas the texture page comes from GP0(E1). Treating those texture
words as RGB555 produced a false rasterization and must never be used as
original-frame evidence.

A *separate*, owner-local full-frame replay experiment used the real
preframe VRAM and first-frame native GPU GP0 packet sequence, independently
reconstructed the postframe memory, and compared it with the detached
PCSX-Redux Player's Frame 1 snapshot. After 8bpp interpretation, **all
524,288 16-bit VRAM words matched exactly**. The source screenshot remains
the independently captured GUI image from Stage518, not a manufactured
render of the replay buffer. No game bytes or private digests belong here.

## Strict ROM-free implementation

`tools/replay_private_gp0_intro_8bpp.py` intentionally supports a
**narrow subset**:

- GP0(00) canonical NOP; E1/E2/E3/E4/E5/E6 state register setting
- GP0(02) nonwrapping RGB555 VRAM clear/fill from Stage522
- GP0(66) variable-size indexed **8bpp** textured rectangle with
  modulation of a 5-bit CLUT channel by the 8-bit GP0 tint channel
  using `(channel5 * tint8) >> 7`, saturation and optional ABR1 B+F
  semitransparency when the CLUT texel's bit15 is set
- Mask mode off, texture window zero, draw offset zero, no texture flips,
  explicit GPU drawing bounds, an in-bounds full 256-entry CLUT, and no
  overlapping sampled texture/CLUT regions with the sprite destination

GPU states outside the supported subset, truncated/noncanonical command
packets, unmodeled raster primitives, VRAM wrapping, unknown texture
window, mask modes, arbitrary draw offsets and texture feedback hazards
**fail closed**. The module consumes user-supplied bytes and complete
packet lists; it does not download, read, publish or attest a game dump.
Tests use only artificial VRAM, palettes and GP0 words.

## Independent verification and limitations

The original-game comparison remains **owner-private**. Local verification
checks the manifest and all archived file digests; authentic native
preamble/first-VSync framing and independent GUI screenshot provenance are
separate gates. A full VRAM match proves this specific trace's memory
effect under the captured PCSX-Redux software GPU, not compatibility with
all GP0 modes or physical PS1 hardware.

The Stage516 complete five-input seal is still OPEN because the genuine
GUI-exported native V2 file has not been obtained from the updated
AppImage. Likewise, Surf Village field rendering/geometry is NOT proven
by the Sony intro frame. This PR is deliberately stacked on Draft PR
#141 and remains Draft pending CI and authenticated owner-only witness.
