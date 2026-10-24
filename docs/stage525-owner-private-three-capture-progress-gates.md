# Stage525 — three-capture progression: early boot → publisher → developer logo

This stage compares **three authentic, independently archived** Wild Arms
(USA) PS1 GPU snapshots from the owner-private Stage517 capture. Each ZIP
entry was CRC-checked and verified against an owner-private file-integrity
manifest before reading the native `PSXGPUDUMPv1r1` typed packet records.

The private audit validates:

- one GPU version-2 record and exactly one native TraceBegin;
- a full 1 MiB pre-trace GP0(A0) VRAM snapshot identical to the independent
  detached Player rewind for each captured interval;
- six ordered GP0(E1–E6) restoration words and exactly three completed
  native VSync records in each dump;
- native live GP1 controls are only repetitions of uniquely observed
  pretrace controls (never guessed as no-ops);
- all first-live-VSync GP0 transport words can be split into complete
  GPU packets using bounded opcode-specific word counts.

## Confirmed progression (without disclosing original payloads)

| Capture checkpoint | First-frame GP0 words | Complete packets | VRAM proof |
| --- | ---: | ---: | --- |
| Early boot/startup | 0 | 0 | No live GPU writes; detached pre/post 1 MiB buffers match |
| Sony/publisher intro | 33 | 19 | Stage524 bounded 8bpp CLUT GP0(66) replay matches the complete 524,288-word Player Frame1 VRAM |
| Developer-logo interval | 43 | 19 | GP0 packet boundary checks pass, **not rasterized by Stage524** |

The developer-logo interval contains additional **GP0(2C) textured polygons**
and **GP0(64) textured rectangles** not admitted by the current Sony-intro
renderer. Even if detached frame-1 VRAM equals the pretrace buffer,
**this does not authenticate execution of the unknown graphics
primitives**. Silent skipping of commands would create false parity.

Two synthetic tests were added that explicitly require failure on both
opcode classes; another test refuses a partially supported frame followed
by an unsupported GP0(64). Original game bytes, native GP0 words, private
game serials, hashes, VRAM and screenshots are never committed to CI.

The owner-only Drive archive stores `Stage525_private_three_capture_progression_audit.py`
and its private JSON manifest report, verified again after downloading.
This is evidence continuity for *intro/developer logos*, **not Surf
Village** or an original gameplay replay.

## Following gates

1. Complete PCSX-Redux AppImage build with intact native host tests.
2. Obtain the real GUI-exported V2 frame file and finish independent Stage516
   strict five-input binding; no synthesized V2 may replace that evidence.
3. Add GP0(2C)/(64) rasterization only with exact native semantics and
   byte-exact negative/positive tests, then authenticate original captures.
4. Navigate the game to genuine Surf Village using privately captured
   runtime evidence before claiming that field graphics are correct.

Until then the Stage516 seal and Surf Village remain **unverified**.
