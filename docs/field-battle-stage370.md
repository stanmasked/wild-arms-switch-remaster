# Stage 370 — in-game warning when both battle save copies are corrupt

Stacked on [PR #59](https://github.com/stanmasked/wild-arms-switch-remaster/pull/59), whose exact-head NeXium verified **12/12 real guest checks** for fail-closed recovery when both WABJ A/B CRCs are wrong.

## New player-facing behavior

At NRO startup the game already reads the independent two-slot battle journal.
The additional *read-only* severity flag is raised **only** if the loader
returns `BattleJournalStatus::Corrupt`. This means that neither saved copy
could be trusted. The game never guesses from the invalid bytes, silently
overwrites the files, or pretends to have restored earned EXP/Gella.

The warning is deliberately visible **only while holding ZL** on the manual
exploration field, above the existing history/reward panel:

- `BATTLE SD INVALID`
- `NO AUTOSAVE - KEEP FILES`

The red-edged dark panel occupies native coordinates x=690..1239,
y=554..608, leaving the history panel starting at y=612 intact.
It is not drawn during normal field exploration, active combat or autoplay.
It also does **not** appear on a fresh empty journal (Missing), successful
load from intact A/B (Loaded), or single-slot degraded-but-valid fallback.
There are no new inputs, save record changes, or asset/ROM dependencies.

A platform-neutral C++ unit test checks the exact status mapping, text and
border pixels, the absence of writes when inactive/invalid raster geometry,
and unchanged pixels everywhere outside the warning rectangle, including
stride padding and sentinel guards.

## Limitations

The original four wins/32 EXP/48 Gella shown in the test-only prototype
remain **unrecoverable from two simultaneously invalid CRC records alone**.
The notice asks players to keep the bytes for manual restoration using an
independently preserved original; it is not a recovery button. Firmware,
original PS1 game content and hardware Switch SD-card durability are not
included. CI must independently confirm the new host tests, NRO, and
NeXium image audits.
