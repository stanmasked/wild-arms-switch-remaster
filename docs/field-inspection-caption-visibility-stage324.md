# Stage 324 — restore visibility of the inspection caption

## Evidence from the failed Stage 323 NeXium guest

[NeXium Actions run 39331735706](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39331735706)
actually booted the asset-free NRO, rendered guest game frames, and passed
the five-scene parity and independently restarted SD recovery checks.
However, the **new** entire 238×55-pixel inspection caption audit failed.

The raw screenshot artifact (ID `12223614707`) was downloaded and
inspected. Its four additional PNGs clearly reveal the cause:

- `07_previous_caption_expired` and `10_revisit_expired` still show
  NeXium's opaque FPS/cycle statistics at the top-left, overlaid on
  the game viewport. The old baseline sample at native (20,34)
  therefore reads the *emulator HUD*, not the game's clear background.
- `08_revisited_noted` visibly contains the expected blue caption
  with the text CLUE NOTED under that HUD, but the HUD obscures some
  of the glyphs and border. An exact comparison of every panel pixel
  is fundamentally impossible at that position.
- The clue count remained 1/2, the event outline was rendered,
  and the player stayed at the expected adjacent tile.

This is a **UI placement / test-observation conflict**, not evidence
of broken gameplay progression or failed NRO compilation. Do not
misreport the failed NeXium workflow as successful.

## Resolution

Move the authored gameplay inspection caption from native x=20 to
native **x=1000** (same y=34; 238×55 pixels), inside the empty
upper-right viewport margin, away from the persistent NeXium HUD.
This also makes the message actually readable during emulator play.

Update the independent Python oracle and synthetic screenshot
fixtures to compare the **entire unoccluded** right-side panel,
including the complete CLUE NOTED glyph pixels. The two blank
caption baseline checks now sample native (1000,34). Add a negative
test flipping one visible panel pixel to prove the full-panel
comparator remains strict rather than masking the obstructed area.

The original gameplay mechanics, maps, session journal and 40-byte
v1 world save codec are unchanged. The resulting desktop screenshots
will need an exact-head *new* NeXium run before calling Stage 324
fixed and verified on the guest. Host CTest/NRO are separate checks.
