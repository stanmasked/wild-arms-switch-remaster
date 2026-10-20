# Stage 338 — isolated turn-battle core

Adds a deterministic, asset-free native C++ model for a three-member
party against two synthetic enemies. This is NOT reconstructed Wild Arms
gameplay, original PS1 statistics, or a finished Switch battle screen.

- A living hero selects **Strike** (living enemy target) or **Guard**.
- Damage is max(1, attack - armor), clamped to remaining HP.
- Guard halves incoming damage, rounding up, for the current round.
- Each hero may act once. After all living heroes act, living enemies
  respond in stable slot order, cycling targets and skipping fallen heroes.
- Finishing the last enemy ends the battle immediately without retaliation.
- All invalid states/inputs and round counter overflow leave state unchanged.
- No RNG, heap, I/O, frame rendering, original ROM assets or saved state.

The module deliberately has no field encounter triggers or framebuffer
integration yet. It compiles on the host and with the Switch C++ toolchain,
and is independently exercised by the new CTest entry
wa_field_battle_tests. Existing field, journal, and save paths remain
untouched. Emulator or hardware playability is not implied.

## Stage 339 — independent battle input adapter

An additional header, `field_battle_controller.hpp`, maps sampled
button states to one deterministic battle action per new press.

- Left/Right selects an available hero; Up/Down selects a living target.
- The cursor wraps and skips fallen/already-acted participants.
- Confirm performs one strike; Guard performs one defend action.
- Held buttons cannot issue additional attacks or move the cursor.
- A frame containing navigation and an attack chooses navigation only.
- Simultaneous Confirm+Guard and contradictory direction presses
  produce no combat action.
- Corrupt battle state or cursor is rejected without any mutation
  of either battle state or button-edge latches.
- Completed battles do not accept further actions.

A new host `wa_field_battle_controller_tests` CTest target covers
navigation, edge latching, guarded rounds, victory and invalid commands.

This is platform-neutral groundwork only. No mapping to physical Switch
buttons or battle UI is claimed; no modifications to field exploration,
NeXium screenshot references, NRO runtime or save serialization.

## Stage 340 — read-only battle framebuffer

A portable, deterministic 1280×720 pixel renderer displays three party cards and two enemies with numeric HP, proportional health bars, selected unit/target borders, current round, READY/ACTED/GUARD/DOWN status, command legend, and victory/defeat overlays. The renderer checks the battle, cursor and pixel target before any writes, never mutating the underlying battle or saved state. It uses an original 5×7 synthetic bitmap alphabet; no PS1 assets are included.

The new `wa_field_battle_view_tests` covers golden geometry and colors, proportional bars, selected units, deterministic full-frame parity, invalid input no-write behavior, framebuffer stride sentinels, and result overlays. `wa_field_battle_capture` exports synthetic host-only initial/guard/victory PPM frames. A separate workflow converts them to PNG using a Python standard-library script, retaining provenance as **host reference screenshots, not NeXium or real Nintendo Switch captures**. No change to the existing playable exploration NRO or its save format.

## Stage 341 — optional interactive battle mode in the Switch NRO

A separate `FieldBattleSession` owns its own temporary combat stats,
cursor and button latches. On a real Switch in **manual exploration**,
tap **R** to open a new synthetic battle. While it is open:
**D-pad Left/Right** selects a ready hero; **Up/Down** selects a living
opponent; **A** strikes; **Y** guards; **B** closes the battle and returns
to the exact live field state. **Plus** still exits the homebrew.

Battle owns the controller sample: the existing field runtime advances
on a **neutral pad frame** so its timing remains valid but a battle A/Y/B
does not inspect or acknowledge world events, change maps, or write a
quicksave. Opening R while the autoplay demonstration is running is
ignored. R+A on entry cannot attack until A has been released; holding
A during later frames never repeats an attack. Returning to R starts a
fresh synthetic encounter rather than reusing the previous encounter.

New `wa_field_battle_session_tests` cover entry/reentry and exit,
input ownership, same-frame R+A edge latching, actual visible HP damage,
guard sentinel pixels, and validation failures without screen or state
writes. The Switch source **now includes** the battle HUD and mode selector;
compilation and actual execution in NeXium or physical Switch must still
be confirmed by the new exact-head CI. No original PS1 sprites, music,
encounter triggers, saves, or completion storyline are claimed.

## Stage 343 — independent real NeXium battle guest check

The experimental `nexium-smoke.yml` workflow retains its original
five-guest save-recovery sequence and the unchanged five canonical
exploration screenshots. After the existing GUI-only no-NRO comparison,
it now boots the **same NRO in a sixth isolated NeXium process** with
a different `NEXIUM_DATA_ROOT`. This prevents field save validation
from being affected by the new battle input test.

With the official emulator's default keyboard assignments (`R=E`,
`A=C`, `Y=Z`, `B=X`) the test cancels autoplay, takes a field
screenshot, opens battle, attacks once, keeps A pressed across two
captures, defends with Y, then closes with B. A Python oracle checks
the real observed Xvfb pixels, including selected borders, enemy HP
bar shrinkage, absence of repeated held-A damage, guard cursor change,
and identical field image before/after. It records SHA-256 of six PNGs
in `nexium-probe/battle-audit.json` and includes them in the existing
workflow artifact.

Seven independent synthetic positive/negative tests exercise the
oracle's fail-closed behavior before guest launch. These checks are
new and are **not yet verified by a completed exact-head NeXium run**.
NeXium Xvfb screenshots are not native framebuffer captures or
evidence of physical Switch hardware.

## Stage 346 — genuine sixth NeXium guest battle screenshot

The first completed sixth-process NeXium guest [run 39385814137](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/39385814137)
produced **all six real screenshots**, with **five of six** independent
conditions passing. The guest visibly opened battle on R, damaged foe
HP on A, did not repeat during held A, advanced the selection on Y
guard, and restored pixel-identical field ROI after B.

The sole rejected condition read blue from native point `(70,120)`,
which is underneath NeXium's separately rendered FPS/performance HUD.
The actual desktop screenshot shows RGB `(60,212,92)` there instead
of the native border's `(105,160,230)`. Two exposed positions along
the SAME selected player's left-side border, `(70,220)` and `(70,245)`,
were inspected directly in the archived guest PNG and **both matched**
RGB `(105,160,230)`. The enemy selection and HP check remains
unchanged. No image or gameplay masks were expanded or loosened.

The independent auditor now requires both exposed blue samples, plus
the original full-health red foe bar and selected gold frame. Two
new adversarial synthetic cases require acceptance despite NeXium's
HUD occlusion and rejection when an exposed border pixel is missing.
This is a precise correction to the screenshot oracle, **not** a
change to the Switch renderer or battle controls. A fresh exact-head
CI run is needed before the corrected audit can be called green.
