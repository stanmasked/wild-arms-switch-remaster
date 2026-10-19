# Stage 317 — require separate A inspection and B clue recording

The two authored synthetic events require an explicit inspection with
Switch A (while facing an adjacent event marker) followed by a separate
Switch B action to record the clue.

## Previously

When A and B edges were delivered in the *same* frame, the manual
world emitted a fresh A inspection and the runtime immediately
consumed that newly created inspection in its B branch. This silently
collapsed the two intended actions into one chord.

## Corrected rule

The B recording branch now requires `outcome.inspected ==
Trigger::None` as well as the existing valid, visible, adjacent
event inspection and unchanged player position/facing checks.

A+B on the same frame may display the inspection but **does not**
collect or increment the journal. B pressed on a subsequent frame
can record that same 900ms inspection. Ordinary separate A then B
and subsequent idempotent revisit behavior are unchanged.

## Regression and compatibility

`test_simultaneous_A_and_B_cannot_collect_before_inspection` starts
beside the area-0 marker at (4,1), presses A+B in one frame, asserts
inspection without any clue recorded, then presses B separately
within the inspection timeout and requires a single valid clue.

The test checks framebuffer stride/tail guards. No game ROM or
licensed graphics is added, and the v1 40-byte save codec is unchanged.
An exact-head successful Host CTest and NeXium guest audit are still
required before reporting these changes as passed.
