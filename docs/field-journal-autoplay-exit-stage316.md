# Stage 316 — protect autoplay → manual journal handoff

The manual field now preflights the world snapshot and all discovery
entries before handling inputs. Autoplay, however, deliberately ignores
the dormant session journal, because its scripted world route does not
use recorded clues.

Previously, pressing B during autoplay reset the manual world and
returned to manual mode without validating that dormant ledger.
If the ledger became malformed while autoplay was running, one
apparently successful handoff left an invalid manual runtime.

## Fix

The autoplay B-cancel transition validates the **entire** discovery
journal before writing any manual world state or framebuffer. On
failure it returns `InvalidSimulation`, without advancing the
committed frame tick, ending autoplay, or drawing partial pixels.
On success it retains valid session clues when returning to manual
play, just as it did before this change.

## Reproducible host regression

`test_autoplay_exit_rejects_corrupt_discoveries_transactionally`:

1. Record a valid clue and start the scripted demo.
2. Inject an invalid second entry while autoplay is active.
3. Press B. Assert fail-closed result, pixel and time identity,
   preserved autoplay mode, and unchanged manual position.
4. Repair the second entry. Press B again at the same tick.
5. Assert successful transition to a fresh manual starting point
   with both legitimate session clues still present and valid.

The test uses only the two authored synthetic maps; it is *not*
evidence of original game resource extraction, actual NeXium
execution or real Nintendo Switch hardware testing.

The v1 save layout (40 bytes) is unchanged.

## Status

Changes are committed to Draft PR #34 and registered in the existing
host CTest executable. GitHub Actions results are required before
calling the new regression tested or NeXium guest-confirmed.
