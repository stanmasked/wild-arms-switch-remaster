# Stage 308 — in-session field clue journal (synthetic gameplay)

The player can inspect a neighboring `!` event with **A**, then press **B**
while the inspection is still visible to record that clue. The key is
`(area, x, y)`: revisiting the same event does not add duplicates.

**Hold L** to open the journal. This new, read-only overlay shows
`CLUES collected/available` and one line per found clue, e.g.
`A0 X4 Y1`. Releasing L closes the view. While L is held, manual movement,
event acknowledgement, B collection, Y quicksave and Minus quickload are
not executed. The view always draws from the same portable renderer used by
the Nintendo Switch build and host tests. Autoplay mode ignores L, preserving
the original five reference frames.

The journal has a fixed maximum of 16 entries; the renderer validates every
entry and rejects malformed area/coordinate keys and repeated keys before
writing to the framebuffer. The 1280x720 RGBA overlay uses original tiny
bitmap glyphs; there are no copyrighted game assets. The count of available
events is calculated from the two synthetic demo maps.

The journal is **session-only**. Pressing Y or Minus still stores or restores
the unchanged 40-byte world save; clue entries are *not* written to SD.
A new app process starts with a new empty journal. This is intentional until
a separate, versioned save-schema migration is designed and tested.

## Verification

- `wa_field_journal_view_tests`: empty view, 1/2 and 2/2 recorded clues,
  deterministic overlay pixels, padding guards, malformed target, invalid
  marker, duplicate and out-of-bounds ledger rejection without writes.
- `wa_field_runtime_tests`: L freezes movement and snapshot actions,
  B+L cannot record, releasing L restores B recording, and corrupt journal
  preflight does not mutate the timer or framebuffer.
- Existing field capture, host regression and Nintendo Switch cross-build
  workflows should remain unchanged; CI must be checked on the exact commit.
- The NeXium workflow is an experimental emulator verification; a green
  workflow is not evidence of a physical Nintendo Switch hardware test.
