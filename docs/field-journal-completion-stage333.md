# Stage 333 — exploration complete reward

This step builds on Stage 332 (`a690ce69`) in an **isolated
follow-on branch**, leaving Draft PR #34 and its pending NeXium
run untouched.

The held-L journal now shows **ALL CLUES FOUND** in the lower
panel after both authored synthetic discoveries are recorded
by separate A inspection + B collection. The banner is not
displayed at 0/2, 1/2, on repeat collection, or for worlds
containing no authored events.

The condition is calculated from the previously validated in-session
journal and the actual world event markers, with no save-format,
progress-state, controls or original PS1 resource changes.

The message starts at native (340,600), inside the panel border,
below the bottom of the capacity-16 journal entry layout (last
description ends around y=566). It uses the existing 5x7 font.

Regressions cover the full 0 → 1 → 2 clue sequence, duplicate
idempotency, completion F glyph, no journal mutation, corruption
rejection without pixel writes, framebuffer guards, and an actual
controller-driven two-area journey reaching 2/2.

Current NeXium first-guest journal oracle only observes 0/2 and 1/2;
it must remain unchanged. An additional 2/2 guest capture would be
needed before claiming emulator-side completion-banner verification.
All scene content is independently authored and not from Wild Arms.

## Stage 334 — explicit guest proof of the 2/2 completion goal

A dedicated continuation of the same real guest NRO process now runs
*after* the original pending-event save and restore evidence, travels
to the area-0 exit and area-1 clue by actual D-pad controls, inspects
A and records B, then holds L for completion. Five extra screenshots
in `nexium-probe/field-completion` capture the second map, pre-B
one-clue journal, completed two-clue journal and field badge.

The independent image oracle now renders **2/2** in the full 672x560
journal overlay, including both notes, the two separate 1/1 counters
and **ALL CLUES FOUND**, and requires exact RGB equality. A separate
six-condition auditor also verifies the guest actually reached (4,2)
in the second region, that the second event was uncollected before B,
that the full second-area badge appears only after recording and that
the player stayed put. Synthetic negative tests reject an incomplete
journal, a changed banner pixel, an absent badge, a moved player or
missing screenshots. All evidence is stored as hashed actual Xvfb PNGs.

Stage 336 independently verified this exact 2/2 guest route at commit
`36b33b17`: NeXium [run 39347668322](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39347668322)
passed all six completion checks, five ordered image checkpoints and
cross-process storage regression checks. Host Core passed 125/125,
and the Switch NRO build completed. These are emulator desktop
(Xvfb) observations, **not** physical Switch verification or proof of
fidelity to original PS1 assets.

## Stage 337 — complete sprite-tile immobility and stronger negative tests

Retain the same six-condition 2/2 guest audit, but strengthen its final
player-stationary condition. The before-and-after screenshots now require
**all RGB pixels of the projected area-1 player tile (4,2)** to remain
identical. This tile ends before the adjacent event badge and cannot be
confused with the legitimate change to the event tile (4,3).

Three new synthetic adversarial fixtures verify fail-closed behavior:
an erased `AREA 1 1/1` line, erased second-clue narrative details,
and a corrupted player sprite region that still retains the original
single red sampled pixel. Existing six conditions and screenshot names
are unchanged, so the earlier guest proof remains comparable.

Stage 337 is **not yet NeXium-verified** until its new exact-head CI
completes. Only the evidence checker and fixtures changed: no game
logic, map geometry, Switch input mappings, original PS1 content,
or save serialization were modified.
