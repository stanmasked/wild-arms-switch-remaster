# Stage 323 — independent NeXium proof of immediate CLUE NOTED revisit

Stage 322 modified the manual runtime so that A inspection of an
already-recorded event immediately renders a blue CLUE NOTED caption.
The Stage 322 exact-head host/NRO and NeXium workflows passed, but
the existing NeXium guest screenshot sequence exercised only initial
A inspection, B collection, and L journal use: it did **not** prove
that a subsequent A alone displayed the new caption.

This stage extends the same first guest, after the seven existing
journal screenshots and before the second pending-event save:

- First wait for the *previous* 900ms blue caption to disappear. Save
  `07_previous_caption_expired.png` and require bare background RGB.
  This prevents a stale overlay from creating a false positive.
- Revisit the same marker by pressing A without any new B. Save
  `08_revisited_noted.png`.
- Reopen L while at the same player position; save
  `09_revisit_journal.png`. The panel must still read exactly 1/2.
- Release L and let the new 900ms caption expire; save
  `10_revisit_expired.png` without moving.

The independent Python audit now compares the **complete projected
238×55 caption panel RGB**, including the full CLUE NOTED glyphs,
to an independently authored original bitmap-font oracle; verifies
the event outline, the unchanged one-clue journal and a still red,
unmoved player after caption expiry. The comparator uses the existing
observed 1600×900 Xvfb/NeXium geometry, not the in-process C++ pixels.

Four additional synthetic negative tests reject a stale blue caption
before the new A press, missing caption glyphs, an incorrect clue count
on journal reopening, and a moved player after revisit. None of the gameplay core,
40-byte v1 save payload or authored two-map world is modified.

**Evidence boundary:** This changes the experimental guest automation
and independent audit; exact-head CI must pass before calling Stage 323
guest behavior confirmed. Original Wild Arms game assets are not
present, and physical Nintendo Switch testing is not performed.
