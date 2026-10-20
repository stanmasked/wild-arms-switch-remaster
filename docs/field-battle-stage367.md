# Stage 367 — earning and reloading rewards after CRC recovery

Depends on Stage366 PR #56: NeXium guest 17, reusing actual SDMC
across guests 14/15/16, repaired corrupt latest generation-3 A
without changing prior generation-2 B. At the start of Stage367
the saved battle journal reports 2 wins, 1 retreat, 16 prototype EXP,
and 24 prototype Gella.

Two MORE guest processes, still sharing that exact SDMC:
- Guest 18 observes the restored 2-win reward panel before combat,
  performs 7 distinct A strike presses versus full-health foes, observes
  an actual VICTORY, closes B once and sees 3 wins, EXP 24, Gella 36.
  The first journal A generation 3 stays byte-identical. New B
  generation 4 records 3 wins and 1 retreat.
- Guest 19 independently boots the same SDMC, verifies the unchanged
  entire 3-win reward panel before any battle, then R/B retreats. Its
  new generation-5 A must show 3 wins, 2 retreats, EXP 24, Gella 36;
  prior generation-4 B must be byte-identical.

An independent Python oracle requires exactly five real Xvfb frames,
six immutable valid WABJ files with both CRC layers checked, six
distinct guest process PIDs across stages 365/366/367, and exactly
seven A key edges in the correct event sequence. Pixel checks on
5x7 font digits distinguish WINS 3, EXP 24, G 36 from WINS 2,
EXP 16, G 24. The entire reward panel must survive reboot unchanged.

Sixteen synthetic tests cover tampered/absent frames, duplicate
processes, wrong input sequence, wrong rewards or journal generations,
corrupt CRC, and altered map/earlier journal slots.

This is a nonstandard emulator-only loader experiment with ROM-free
placeholder rewards, not verification of the PS1 economy, physical
Nintendo Switch use or physical SD power-loss safety.
