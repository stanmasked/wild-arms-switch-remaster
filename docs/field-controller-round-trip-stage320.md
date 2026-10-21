# Stage 320 — complete two-area controller round-trip

This stage extends the Stage 319 synthetic field integration test
from a one-way area transition into a **full area-0 → area-1 → area-0**
round-trip, without injecting player coordinates, triggers or clocks.

## Executed controller plan (test definition)

- Start area 0 at (1,1), press Right twice, inspect the event (4,1)
  using A and separately record the first clue using B.
- Follow `DDDRRDR` to the first authored exit at (6,5). A acknowledges
  the transition and area 1 begins at (1,1).
- Follow `RRRD` to (4,2), inspect the adjacent event (4,3) using A,
  then B records the second clue.
- Follow `LLDDDRRRR` from (4,2) via (2,2), (2,5) to the second
  authored exit (6,5), **avoiding** the event tile at (4,3).
  Confirm with A to return to area 0.
- Move Right twice from the returned entrance (1,1) to (3,1);
  a fresh A inspection and subsequent B on the original clue must
  return `clue_already_recorded`, never a third clue.
- Hold L to inspect two ordered journal rows; quicksave/quickload
  must preserve both session clues. A genuinely new runtime starts
  with an empty journal.

The test asserts **24** successful controller-driven steps,
both area transitions, pending exit acknowledgements and unchanged
two-clue idempotency on revisit. The render buffer has stride/tail
guards. No synthetic state jump is permitted in the journey.

This test is run by the existing `wa_field_runtime_tests` CMake/CTest
registration and uses only the original asset-free sample maps.

## Verification boundary

The repository commit does not prove successful execution. At the
start of Stage 320, exact-head Host Core, Switch NRO, and NeXium
runs for Stage 319 remained queued. Separately, the **Stage 318
host field-capture reference** workflow run 39323660091 passed;
that is image-reference evidence only and is not a pass for this
cross-area integration test. Do not infer physical Switch behavior.
