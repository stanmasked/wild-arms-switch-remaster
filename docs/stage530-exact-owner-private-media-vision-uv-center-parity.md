# Stage530 — PCSX-Redux GPU polygon pixel-center UV: exact developer-logo parity

The original Wild Arms (USA) Media.Vision logo capture has two GP0(2C)
flat-shaded, 4bpp CLUT textured quads (256x128), followed by two GP0(64)
opaque indexed sprites. The original GPU dump, detached real-GUI native
Frame1 V2, raw VRAM and all derived screenshots remain owner-private.

## Corrected root cause and bounded algorithm

The previous Stage528 polygon used **sprite-style texture sampling**
`U=U0+pixel_x`, `V=V0+pixel_y`. A PS1 polygon does **not** sample its
far UV vertex directly at its far-right/bottom pixel. In the restricted
canonical axis-aligned affine case, vertex UV extent is width-1 texels
over **width pixel cells**. The pinned PCSX-Redux
`src/gpu/soft/polys.cc` computes fixed-point gradients and seeds spans
with a `+0x8000` pixel-center bias. For these exact constraints:

```text
gradient_u_16_16 = floor((width - 1) * 65536 / width)
gradient_v_16_16 = floor((height - 1) * 65536 / height)
sample_u = (u0 + ((pixel_x * gradient_u_16_16 + 32768) >> 16)) & 255
sample_v = (v0 + ((pixel_y * gradient_v_16_16 + 32768) >> 16)) & 255
```

A 256-pixel polygon with U vertices 0..255 samples U=254 on its last
pixel, not 255. A 128-pixel polygon with V vertices 0..127 samples
V=126 on its final row, not 127.

The Stage530 public model changes only this bounded GP0(2C) UV rule.
GP0(64) indexed *sprite* sampling keeps its original direct U/V
increment; GP0(66) Sony-intro behavior remains unchanged. The polygon
still rejects arbitrary tilted polygons, noncanonical UV corners,
unsupported CLUT/tpage/bounds/feedback, texture windows and offsets.
No general triangle rasterizer or universal PS1 compatibility is claimed.

The pinned PCSX-Redux flat-shaded textured polygon dispatch takes its
solid packed-color fast path even if E1 dither bit9 is set. Accordingly,
Stage528's global refusal based only on that flag was too broad;
Stage530 removes it **only for GP0(2C) flat-shaded textured quads**.
Other GPU primitives do not inherit that exception.

## Original-game independent parity evidence — OWNER-PRIVATE

Owner-only Stage530 compares several **independent** first-frame
replay hypotheses, all using the same archived first-frame GPU packets
and initial detached VRAM. The actual real-GUI native V2 from Stage528
is separately authenticated by its binary magic, frame number, native
dump SHA-256 and CRC32. This genuine observed Frame1 VRAM equals the
owner-private previous detached capture, not a synthesized V2.

Against **all 524,288 16-bit words** of actual observed detached Frame1,
with original packet order and no other game input modification:

- missing GP0(2C) polygons: 19,198 mismatches;
- naive sprite-style U/V increment: 10,564 mismatches;
- truncated polygon gradient without pixel-center bias: 10,574 mismatches;
- **16.16 gradient plus pixel-center bias: 0 mismatches**.

The zero-mismatch result proves bit-exact VRAM **for this captured
Media.Vision first frame and this pinned software GPU runtime only**.
It does not authenticate original screenshot origin cryptographically,
nor prove tilted polygon GPU coverage, arbitrary E1 modes, hardware PS1
parity, all developer-logo frames or Surf Village gameplay.

## Synthetic public regressions

`tests/test_gp0_2c_pixel_center_stage530.py` covers 256-wide and
128-tall UV endpoint behavior, width=4 vs width=2 rounding,
flat-shaded dither-bit equivalence and malformed UV rejection.
Updated Stage528 synthetic quads expect the correct last-pixel texel
and retain all prior fail-closed tests. Public CI contains **no**
authentic game data, captured GPU words, VRAM, private filenames or
game-derived hashes. All original materials and reproducibility
scripts stay in owner-only Google Drive.
