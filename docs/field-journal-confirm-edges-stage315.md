# Stage 315 — L-modal A-edge suppression

In manual field gameplay the held L journal is modal. Previously it
suppressed A *actions* but left `PadDecoder.confirm_down` unchanged.
If A was first held while L was open, releasing L without releasing A
could synthesize an unwanted fresh A edge, inspecting an adjacent ! or
acknowledging an event trigger.

On every L-held manual frame the game now updates only the existing
input-edge decoder (`manual.decoder.confirm_down = pad.confirm`),
in addition to resetting partial directional movement cadence. It does
not perform any world movement, inspection, trigger acknowledgement,
clue collection, quicksave or quickload while the journal is visible.

The edge decoder reflects the physical held state. Keeping A held while
releasing L cannot cause an action; releasing and genuinely pressing A
again produces a new event. When A is released *during* L, its decoder
state resets so a new press outside the modal works normally.

`test_l_modal_does_not_replay_held_A_on_release` covers both:
1. adjacent authored event A inspection from x3,y1 facing Right;
2. an already-pending event at x4,y1 requiring a fresh A press.

It confirms no operation occurs on an L-release with A held, then
verifies an independent release+press does perform the expected action.
RG/BA framebuffer guard bytes are not mutated outside writable region.

**Save compatibility:** This uses the pre-existing `PadDecoder` input
bit in manual `WorldState` and does not change the 40-byte v1 schema,
its decoder encoding, scene data, or journal graphics.

**Verification:** GitHub commit + CTest registration alone do not
prove a successful host build, guest NeXium run or physical Switch test.
Only exact-head successful CI results provide that evidence.
