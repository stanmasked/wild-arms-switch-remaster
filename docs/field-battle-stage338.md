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
