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
