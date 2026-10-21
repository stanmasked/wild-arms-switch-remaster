# Stage 331 — complete fallback glyph coverage for journal notes

The previous exact-head Stage 328 run [NeXium #39339910568](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39339910568)
completed with success: all 14 independent real guest L-panel checks
passed, including the exact new two-line journal text pixel oracle;
five reference game scenes matched with zero mismatched RGB pixels of
4,112,580 checked. [Host Core #39339915570](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39339915570)
passed all 125 CTests on the same original Stage 328 commit.

## Bug fixed

The neutral text for a future synthetic event, `FIELD OBSERVATION` /
`NO FIELD NOTES`, used **F** and **B** absent from the bounded
5×7 journal font. Those letters would silently render blank. The
two currently-authored event texts were already covered and remain
unchanged.

Add independent B and F 5×7 bitmap glyphs **only** to
`journal_glyph()`, leaving the inspection-caption font and guest
reference text untouched. Add a regression that walks every non-space
character of **all six** title/detail strings (the two authored clues
and fallback), requiring a nonempty bitmap. It also renders the
fallback text on a stride-guarded RGBA8888 surface and checks the
exact F/B pixels.

No map content, discovery journal state, gameplay control, 40-byte
version-1 save codec or licensed original Wild Arms resources change.

**Evidence limit:** Prior NeXium run proves the previous Stage 328
commit; the new Stage 331 commit requires fresh exact-head Host Core,
Switch NRO, and NeXium results to be classified as tested.
