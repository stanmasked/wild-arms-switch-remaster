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
