# Stage 328 — authored field clue notes rather than coordinates

Stage 327 verified the original asset-free two-area field prototype at
commit `dd92cb89` in Host Core (125/125 CTests), Nintendo Switch NRO
and real NeXium guest screenshots (14/14 journal conditions and 0
mismatched pixels in five synthetic reference scenes).

## Player-facing change

Holding L now shows **short narrative findings**, not raw `A0 X4 Y1`
coordinates. Two invented, explicitly noncanonical demo clues are:

| Event key | Journal title | Journal description |
| --- | --- | --- |
| Area 0, (4,1) | OLD RADIO NOTE | SIGNAL IN STATIC |
| Area 1, (4,3) | SILENT RELAY | AN ECHO ANSWERS |

These are **original placeholder narrative notes**, not text
extracted from Wild Arms PS1 or an assertion about its actual plot.

Each collected entry is shown as two 5×7-pixel raster-text lines. The
entire 16-entry bounded journal remains visible in **two columns,
eight entries per column**, with an area prefix in each title.
Descriptions are derived read-only from the authored event coordinate
key; they are not added to the journal data model, save format or
gameplay progress. Unknown future synthetic events get a neutral,
clearly generic note rather than fabricated original lore.

## Regression and evidence

- Full entry-title and description glyph coverage now includes G/R/W,
  and existing I, for the journal's small original bitmap font.
- C++ host tests validate both authored metadata values, dedicated
  first/second text lines, entry order/spacing and target stride guards.
- The NeXium independent *pixel-by-pixel* L-panel oracle now renders
  the original authored notes, not coordinate rows. A synthetic
  tampering test mutates one white detail-text pixel while preserving
  the correct count and border; it **must fail**.
- Scripted autoplay pixels, the L-modal time freeze, clue collection
  and the 40-byte v1 world save are unchanged.

A new exact-commit Host Core, Switch NRO and real NeXium guest run
must pass before this Stage 328 new journal text can be called
tested in the emulator. PR #34 remains Draft.
