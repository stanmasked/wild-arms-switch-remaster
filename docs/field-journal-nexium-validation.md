# Stage 309 — real NeXium L journal audit (experimental)

The native asset-free field NRO keeps the existing host/autoplay screenshot
reference contract, and this stage adds a **separate** manually controlled,
first-guest NeXium capture under `nexium-probe/field-journal/`.

The key mapping is taken from NeXium
[`nexium-gui/src/controller_config.rs`](https://github.com/nexium-emu/nexium/blob/main/nexium-gui/src/controller_config.rs):
Switch L = host Q, A = C, B = X, DRight = Right. Do not assume that
all other emulators use these mappings.

After the already audited `03_start_restored` screenshot (player x1),
the input script:

1. Holds L to capture `00_empty_open.png` and releases it for
   `01_empty_closed.png`.
2. Walks exactly two native 160ms cadence steps, stopping at x3, facing
   the synthetic event marker at (4,1); captures `02_at_marker.png`.
3. Presses A to inspect and captures `03_inspected.png`, then B to
   record that previously unrecorded event.
4. Holds L for `04_one_open.png`; while L remains held it holds DRight
   for 400ms and captures `05_one_open_right_held.png`.
5. Releases L and captures `06_one_closed.png`.

It then follows the existing `04_event_again` to `07_event_restored`
flow unchanged. No new save command is sent during the journal sequence.
The recorded clue is deliberately session-only and cannot be used as
evidence that the existing 40-byte file format persisted a clue.

The independent `tools/audit_nexium_field_journal.py` enforces:

- Exactly seven distinct, bounded 1600x900 **observed** PNGs.
- The exact **full projected RGB journal rectangle** (including every
  glyph of `CLUES 0/2`, `CLUES 1/2`, and `A0 X4 Y1`). Unlike spot
  checks, even one changed compared pixel rejects the proof.
- The player at x3 before and after the modal L+Right action.
- The visible yellow outline for A inspection, and journal closure
  after releasing L.
- An auditable JSON report with seven independent boolean results
  and SHA-256 digests of each observed screenshot.

The font/geometry oracle is authored in Python, independently from the
shared host/Switch C++ renderer. A separate synthetic fixture test suite
covers positive examples, a false clue count, a changed player location,
a **single changed interior UI pixel**, and missing/malformed PNGs.
Those are *invented unit-test screenshots*, not emulator observations.

All real-scene observations use NeXium's established nearest-neighbor
1280x720-to-1234x694 desktop projection in Xvfb. This is neither a direct
capture of the Switch GPU's native framebuffer nor proof of execution on
physical Nintendo Switch hardware. The experimental NeXium loader probe
remains distinct from the valid production NRO.

**No Stage 309 CI or NeXium success is claimed until the exact-head
GitHub Actions workflows complete successfully.**
