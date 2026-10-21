# Stage 318 — synchronize A-held input across modal operations

In addition to the L journal, **Y save**, **Minus load**, and **B exit
from autoplay** are frame-owning UI operations. They must suppress
A gameplay actions on that frame and avoid interpreting the same
still-held A as a brand-new press on the next manual frame.

Before this stage, these modal handoffs bypassed the normal
`PadDecoder` update. In particular, loading a snapshot restored its
historical `confirm_down` bit, rather than the current input state.
An already-held A could consequently inspect the next event or
acknowledge a pending trigger without a fresh key press.

The shared host/NRO field runtime now synchronizes the decoder's
`confirm_down` field from `controls.pad.confirm` after successful
Y save, after valid or empty Minus load, and when B ends autoplay.
Failures remain transactional: invalid states return before modifying
the caller-owned runtime or framebuffer.

Regression `test_modal_save_load_and_demo_cannot_replay_held_A` covers:

1. Y+A held while facing an adjacent event: Y saves, and continuing A
   alone on the next frame must not inspect; release/repress does.
2. An in-memory save of a pending event: A first acknowledges it, then
   Minus+A restores the event; continuing A must not acknowledge it
   again until a fresh release/repress.
3. B+A on return from autoplay: first manual A-held frame cannot
   create an inspection; an actual later A press can.

The same core is compiled for host and libnx Switch NRO. No original
game assets, screen layouts, journals or 40-byte save records change.

## Verification limit

This regression is committed and registered for the existing CTest
executable. Until the exact-head Actions jobs finish, it is not
legitimate to claim successful compilation, passing test output, real
NeXium input replay, or physical Switch execution.
