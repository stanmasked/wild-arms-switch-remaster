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
