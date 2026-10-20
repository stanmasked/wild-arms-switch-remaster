# Wild Arms Remake — Stage368 alternating A/B WABJ CRC faults

Stacked on PR #57, after six distinct NeXium guests have established
a valid stage367 SDMC journal with gen5 A = 3 wins, 2 retreats,
24 prototype EXP, 36 prototype Gella and gen4 B = 3 wins,
1 retreat, 24 EXP, 36 Gella.

Stage368 uses that exact real guest SDMC and three more entirely
independent NeXium guest processes (twentieth, twentyfirst, twentysecond).

- Before guest20, preserve copies and flip ONLY byte 48 (outer WABJ CRC32)
  of newest A gen5. Guest20 rejects it and reloads intact older B gen4,
  restoring 3 wins and 24/36 rewards and 1 retreat. Seven genuine A key
  edges defeat full-health enemies; B closure writes new gen5 A:
  4 wins, 1 retreat, 32 EXP and 48 Gella. Valid B gen4 is unchanged.
- Guest21 reloads 4 wins and 32/48 without further combat, then retreats:
  new gen6 B has 4 wins, 2 retreats, 32/48, old gen5 A unchanged.
- Before guest22, preserve copies and flip ONLY byte 48 of newest B gen6.
  Guest22 rejects it and reloads intact gen5 A (4 wins, 1 retreat, 32/48).
  Guest22 retreats; repaired gen6 B must equal *every byte* of previously
  valid gen6 B. Prior A must also remain byte-identical.

Independent audit requires exactly nine real NeXium Xvfb PNGs,
eight fully CRC-validated immutable WABJ journal copies, two strictly
one-byte CRC faults, nine distinct guest process PIDs across the stack,
16 real keyboard press events including exactly seven A edges,
on-screen victory pixels, and exact bitmap-glyph verification of
"WINS 4", "EXP 32", "G 48" using actual battle font 5x7 masks.
Both rollbacks must preserve winnings; neither retreat may award again.
No unrelated exploration field-save data may be created.

The companion seventeen host-generated positive/adversarial tests do not
constitute proof of guest execution. Game rewards are purely synthetic
prototype values, never original PS1 economy. A NeXium guest SDMC CRC
test does not establish physical Nintendo Switch SD power-cut safety.
