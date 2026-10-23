# Stage522 — conservative GP0(02) first-frame VRAM fill replay

The independent Stage518 authentic INTRO GPU capture includes a native GP0(02)
rectangle fill in the first complete VSync interval. Stage521 established
that some live GP1 controls were exactly equal to their unique native pretrace
restore values, but the Stage437 GP0 packetizer still rejected the fill
opcode. This change adds the **PS1 quick fill** to a strict ROM-free adapter,
not a complete graphics renderer.

## Semantics checked against PS1 GPU specification

- GP0(02) consumes exactly three 32-bit words: 24-bit RGB color/command,
  top-left VRAM address, then width/height.
- X is masked and rounded down to a multiple of 16; width is masked to
  10 bits and rounded up to a multiple of 16 (zero stays zero).
- Y and height are masked to 9 bits. Zero width OR zero height produces
  no memory writes.
- Each red/green/blue 8-bit component is shifted right three bits into
  RGB555 halfword ordering; bit15 is cleared.
- Unlike GP0(A0)/GP0(80), fast fill ignores the GP0(E6) draw/transfer mask.
- This replay rejects nonempty fills wrapping around either VRAM boundary
  and refuses nonzero unused coordinate/size bits. The real hardware masks
  those bits and supports wrapped fills; rejecting them is an intentional,
  documented restriction to avoid false proof in this stage.

## Implemented gates

`tools/decode_private_gp0_fill.py` owns strict fill framing, address
normalization, bounds and 16-bit color conversion. Both the raw GP0
packetizer and the GP0/CLUT trace decoder use this single definition.
The chronological replay writes exact uniform 16-bit pixel rows and updates
known-word epochs without counting a fill as an unmodeled polygon draw.
A fill invalidates *both* direct and transitive GP0(A0) source origin
claims for its destination region. Unchanged/zero-size commands leave
lineage untouched.

ROM-free regressions check channel conversion, 16-pixel geometry, strict
boundaries and reserved bits, fill packet length, masked-zero no-ops,
lack of E6 dependency, post-VRAM equivalence, mismatch rejection,
A0 copy-chain invalidation and a complete synthetic native GPU frame.
Other unknown GP0 operations and live GP1 changes still fail closed.

## Interpretation and next gates

The owner-private Stage518 Intro GPU capture previously exposed a 640x480
non-wrapping fill at origin (0,0), consistent with the newly modeled subset.
That is an *INTRO* record, not a Surf Village capture.

The GP0 timeline replay does **not** rasterize textured/untextured polygons and rectangles, nor authenticate full game scene.
A postframe match is meaningful for wholly modeled memory words only;
unknown polygon framebuffer effects and pixel caches stay explicitly
outside this stage. Stage516 also still requires a genuine GUI-origin V2
and a complete owner-private five-file archive/seal before closure.

All original game data, native GPU dumps, screenshots and owner-private
hashes stay solely in private Google Drive.
