# Stage532 — Rudy character selection to Surf Village: private route integrity gate

## Boundary

Stage531 owner-reported progress reached the **real character-selection GUI** through
PCSX-Redux and retained a restartable selection savestate. It did not establish a
separately audited **Surf Village** original-game field capture. The Stage530
exact UV result is limited to one independently captured **Media.Vision logo**
software-GPU frame; do not extrapolate it to gameplay or all GPU opcodes.

This stage adds `tools/seal_private_rudy_route_stage532.py`, a **public-code,
private-data-only** integrity helper for the next original gameplay route.
It does not run PCSX-Redux, press buttons, prove emulation, recognize Rudy
in screenshots, attest GUI origins, or claim a Switch port is playable.

## Owner-only capture route

1. In the **private** workspace, verify original CUE points to the original
   MODE2/2352 BIN and restore the Stage531 selection savestate.
2. Capture independent unscaled opaque RGB PNG of the character-selection
   screen and retain a copy of the selection state.
3. Record **physical** PS1 controller transitions in an owner-private JSON
   journal. Start at neutral frame zero; use strictly increasing operator-
   declared frame indices and end at neutral. These indices are claims,
   not a trusted emulator timing channel. Observe the on-screen character
   choice and confirm Rudy manually.
4. Select Rudy and play until a **visibly controllable Surf Village scene**
   appears. Independently capture a second unscaled PNG and an arrival
   savestate. Record whether the character responds to directional input,
   and preserve a separate owner-private operator report (not in GitHub).
5. Seal the private bundle, upload files and manifest to **owner-only Google
   Drive**, download independently to a fresh workspace, and run `verify`.
   Keep private originals, states, images, input journals, raw logs, hashes
   and screenshots **out of GitHub and GitHub Actions**.

## Strict input format

The route seal expects these seven **distinct, non-hardlinked, non-symlink**
regular files in one private directory: `disc_bin`, `disc_cue`,
`selection_state`, `selection_png`, `arrival_state`, `arrival_png`,
`input_trace`. Its basename arguments cannot contain directory separators.
The CUE must reference the supplied BIN exactly and contain a single
`TRACK 01 MODE2/2352` and playable `INDEX 01`.

The private input journal schema is:

```json
{
  "schema": "wild-arms-rudy-route-input-v1",
  "origin": "operator_declared_not_attested",
  "events": [
    {"frame": 0, "buttons": []},
    {"frame": 12, "buttons": ["cross"]},
    {"frame": 13, "buttons": []}
  ]
}
```

This is purely a **synthetic illustrative format**, not a verified game
input recipe. The controller mapping for choosing Rudy must be measured,
not inferred from the example. The parser accepts PS1 face buttons, D-pad,
Start and Select; each event uses strictly increasing integer frame indices.
Neither the declared indices nor two different images prove real gameplay.

Private-only command shape (filenames here are placeholders):

```sh
python3 tools/seal_private_rudy_route_stage532.py seal /private/stage532 \
  --disc-bin ORIGINAL.bin --disc-cue ORIGINAL.cue \
  --selection-state BEFORE.state --selection-png BEFORE.png \
  --arrival-state AFTER.state --arrival-png AFTER.png \
  --input-trace CONTROLLER.json
python3 tools/seal_private_rudy_route_stage532.py verify /private/stage532
```

The sealing tool checks raw-file SHA-256, positive and bounded sizes, raw
MODE2 sector alignment, the CUE reference, strict PNG decoding and equal
image dimensions with different RGB pixels, differing state bytes,
unique paths/inodes, input-journal schema and its frame progression.
It writes a **0600 owner-private, no-overwrite, atomic manifest** with
all seven sizes/hashes and a limited summary. `verify` rechecks every
input and recomputes the summary after an independent Drive download.
Neither operation uploads or prints private hashes/data.

## Evidence acceptance — not yet met

- **Integrity PASS** after owner-private `seal`, Drive re-download and
  independent `verify`: file continuity only.
- **Visual gameplay PASS** requires separately observed, unscaled field
  imagery, scene identification, control response, and independent
  comparison to original PCSX-Redux gameplay captures. Synthetic tests do
  not satisfy this gate.
- **Remake rendering parity PASS** additionally requires independent
  replay/visual checks of real Surf Village GPU primitives. The Stage530
  Media.Vision parity is insufficient.

Public CI executes only synthetic, original-free regression fixtures.
