# Stage 319 — controller-driven cross-area journal integration test

The previous cross-area test positioned the player on area 0's exit
tile by directly writing `manual.player`, `manual.pending` and the
movement-clock pause bit. It did exercise the exit *handler*, but could
not establish that a player could reach the exit using real controls.

This stage replaces that test setup with a complete, deterministic
host controller trace across both authored asset-free demo maps.

1. Start area 0 at (1,1); Right,Right moves to (3,1).
2. Press A to inspect the adjacent authored event at (4,1).
   Press B on a separate frame to record clue #1.
3. Run **DDDRRDR**: seven 160ms D-pad steps through walkable
   terrain, ending on the actual E exit tile (6,5), pending exit.
4. Press A to acknowledge the pending exit; only this transition
   changes the area to 1 and restores entrance (1,1).
5. Run **RRRD** to reach (4,2), facing Down, directly adjacent to
   the other authored event at (4,3).
6. A then B records clue #2, with successful movement count 13.
7. Hold L and check both clue glyph rows on the actual host
   RGBA8888 render. Y quicksave and Minus quickload retain the
   *session-only* journal without writing it into the 40-byte
   version-1 world save. A new runtime starts with no clues.

Every player position in this test is reached via controller input,
not direct state mutation. Its path avoids accidental event tiles
until their intended interaction frames.

## Verification and scope

This is a CTest regression in the existing
`test_cross_area_discovery_journal_survives_world_and_snapshot_changes`,
not proof of original Wild Arms maps or a physical Nintendo Switch run.
All locations are synthetic and original licensed resources are absent.
The game save codec and guest runtime are unchanged in this stage.

Registration and source changes are committed in PR #34. Host CTest
and experimental NeXium outcomes are **unverified** while GitHub
Actions jobs remain queued; do not treat the expected path as observed
until executable tests complete.
