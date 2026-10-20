# Stage 342 — independent real guest battle evidence (experimental)

This stage builds on Draft PR #38 (\`stage-341-switch-battle-mode\`),
which adds the **optional** R-open battle screen. The existing long
NeXium 5-process exploration and SD recovery workflow is not modified.

## Why another workflow

A valid NRO build and the successful 128/128 host tests establish
that the battle code compiles and behaves on the host, but **do not
show that NeXium actually receives an R press or renders the HUD**.
The new \`.github/workflows/nexium-battle.yml\` provides a separate,
fail-closed end-to-end experimental guest verification.

Its same-commit inputs are:

- Standard NRO built with devkitPro, without original PS1 resources.
- Host-rendered \`battle-preview-initial.png\` and new
  \`battle-preview-strike.png\` (one native A strike, FOE 1 14 -> 8 HP).
- Pinned NeXium Linux archive and a clearly labeled nonstandard
  compatibility copy, required for the current emulator offset-16
  NRO loader bounds bug (the standard NRO remains unchanged).
- Fedora 44 software Vulkan and a fresh, independent Xvfb guest process.

The automated controller route uses actual default NeXium keyboard
bindings from \`nexium-gui/src/controller_config.rs\`:

1. Capture the initial manual field.
2. Host **E** -> Switch **R**, capture the first battle screen.
3. Host **C** -> Switch **A**, capture the damaged foe and next hero.
4. Host **X** -> Switch **B**, capture the restored field.
5. Host **E** -> Switch **R**, capture a new fresh encounter.

Independent \`audit_nexium_battle.py\` requires:

- All visible game pixels of the initial battle equal the same-commit
  projected host reference, excluding only NeXium's documented
  220x154 performance HUD.
- The one-strike frame exactly equals the host reference, pixel for
  pixel in the visible guest viewport.
- Field pixels before and after the encounter are identical.
- The reopened battle exactly equals its original initial state.
- The field and battle are visually distinct, and the attack causes
  an actual rendered change.

All five Xvfb desktop PNGs, their SHA-256 digests and the JSON report
are captured as experiment evidence. Eight synthetic negative and
positive unit tests exercise the independent audit before NeXium
launch: missed action, wrong field return, repeated damaged state,
tampered game pixel, HUD masking, missing/extra screenshot and wrong
window dimensions.

**Provenance:** this proves an experimental guest screen only if the
new exact-head workflow passes. It is *not* proof of Nintendo hardware
execution, original PS1 fidelity, or the game having authentic
Wild Arms combat, sprites, encounters or soundtrack. Do not mark this
stage complete until GitHub Actions produces the actual report.
