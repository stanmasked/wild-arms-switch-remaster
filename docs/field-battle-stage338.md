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

## Stage 344 — field/battle input ownership integration regression

A separate host CTest target `wa_field_battle_integration_tests`
composes the **actual** `advance_field_runtime` and
`advance_battle_session` on the same 1280×720 RGBA output buffer,
reproducing the Switch `main.cpp` ordering: field draws first with a
neutral controller while battle is active, then the battle overwrites
that frame. Unlike a stand-alone combat test it validates the real
world-state and rendering boundary:

- R+A cannot attack during battle entry or inspect a field event.
- Holding A never repeats a strike; strike reduces opponent HP once.
- Switch Y is a guard action, not an exploration quicksave.
- The field's area, tile, move counter, pending event, clue journal and
  quicksave slot remain untouched through opening, attack, guard, exit
  and reentry.
- After B closes the battle, the **entire RGBA framebuffer exactly
  matches** the same untouched field rendered before entering battle,
  including canary guards beyond the framebuffer stride.
- Manual field D-pad resumes movement from the same pre-battle tile.

No actual Nintendo Switch/NeXium battle screenshot result is implied.
The existing Stage 343 real guest probe is allowed to finish on its
old exact-head commit; Stage 344 is developed as a separate stacked
Draft PR so the exploratory emulator run is not canceled.

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

## Stage 349 — optional deterministic encounters while exploring

The native Switch field prototype now has a **ZR toggled, off-by-default**
synthetic encounter mode. Once enabled in manual exploration, every
`kEncounterStepInterval = 4` *successful* tiles, it opens the same
three-hero/two-foe native battle UI used by R training. R continues to
open a training fight immediately regardless of the encounter setting.
A small golden indicator appears at the top-right only while the
optional mode is enabled, away from the map. A second ZR press disables
it. No random number generator or original PlayStation assets are used.

Encounters are scheduled after the real field runtime has advanced.
Blocked moves, time spent standing still, button-held frames, and
pending event/exit acknowledgments never trigger an encounter.
A pending marker delays the next fight until a later *real movement*.
Entering a new area, restoring a snapshot, or resetting/reversing the
successful movement count re-anchors the interval safely. The scheduler
does not modify the field, clue journal, quicksave, or battle internals.
Autoplay turns optional encounters off, and existing field capture
scripts never press ZR; established reference pixels stay unchanged.

`wa_field_encounters_tests` exercises opt-in gating, exact tile
intervals, pending event deferral, both areas, snapshot rebasing,
R versus ZR precedence, no active-battle toggle, corrupt state refusal
without mutation, and a real shared field-framebuffer/controller
movement → battle-open → B-return integration replay. This is new
Switch gameplay code requiring its own NRO and Host Core CI verification.

## Stage 350 — real NeXium ZR encounter seven-frame evidence

A seventh **independent** guest process with its own isolated SDMC root
now supplements the existing sixth guest R-training battle audit,
without modifying or relaxing the five canonical exploration and
storage-recovery captures. On the actual Switch NRO, NeXium's default
keyboard layout maps ZR to **T**, A to **C**, B to **X** and the D-pad to
the arrow keys. The seventh run confirms that ZR explicitly enables
encounters, three rightward tile steps to the area-0 event **do not**
open a premature fight, A acknowledges the pending event, and the
fourth *real* successful step (left) opens battle. A deals damage and
B returns to the field at the moved tile while ZR mode stays enabled.

`tools/audit_nexium_encounters.py` analyzes exactly seven real
1600×900 Xvfb screenshots and SHA-256 digests, checking a small
gold indicator outside the existing game ROI, pending-event status,
unobscured battle hero/foe borders and HP bars, and the returned
field/player position. The `test_audit_nexium_encounters.py` synthetic
positive and adversarial suite rejects missing frames, missing ZR,
missing event/acknowledgment, missing battle selection/damage, absent
returning player, and any movement on the toggle-only frame. The
NeXium's built-in performance HUD is **not** misclassified as a
missing hero; controls are checked at unobscured native coordinates.

This is **new experimental CI**, not proof until an exact-head NeXium
run finishes with all seven observed guest checks successful. It does
not certify physical Switch, PS1 content, or commercial assets.

## Stage 355 — result classification and session-only battle record

Closing a battle with B now classifies the **validated** terminal phase
and increments a saturating, nonpersistent session counter: `Victory`,
`Defeat` or `Retreat` (closing before combat ends). Every combat
session contributes precisely one result on its **first** closing B edge;
holding B after exit cannot count it twice. The battle still returns to
the exact underlying field pixels, preserving existing NeXium capture
contracts, including ZR's enabled state and the pause/acknowledge state
of any active field event.

The new `BattleHistory` belongs to `FieldBattleSession`, not the
`WorldState`, `FieldSnapshotSlot` or SD journal. Counters saturate at
`UINT32_MAX` rather than wrapping. Opening a fresh fight resets the
combat stats and cursor but **does not reset** the history.

On real Switch/NeXium in manual field mode, **hold ZL** to inspect an
optional read-only battle-history panel showing wins, losses, exits and
the most recent result. There is no panel by default, even immediately
after B, so all existing screenshot tests and save-fidelity invariants
remain unchanged. A later battle screen displays a compact record in
its footer; the first-ever battle screen remains pixel-identical.

`wa_field_battle_results_tests` checks victory through genuine
controller strikes, defeat through enemy retaliation, unfinished-battle
retreat, no double counting, records across new encounters, counter
saturation, HUD opt-in and no writes on invalid targets. This is a
synthetic native prototype, not the PlayStation battle database or an
on-device Switch hardware test; new CI is required.

## Stage 356 — NeXium eighth guest: opt-in result history

A new eighth isolated emulator boot tests actual ZL history-panel
interaction **independently** of the previous five field processes,
sixth R-training and seventh ZR four-step encounter. NeXium's verified
key mappings are ZL=R (host `r`), Switch R=E, and Switch B=X. With
no ZR opt-in, it records seven actual Xvfb screenshots: manual field;
empty ZL history; first R battle; B retreat and same field pixels;
ZL history now displaying `EXITS 1 LAST RETREAT`; ZL released with
the exact original map restored; reopened R battle retaining the prior
retreat in its footer.

The independent Python oracle checks the *pixel font glyph* representing
zero and one in the actual ZL panel, the RETREAT text, unoccluded battle
border, preserved field image and second battle's displayed `E 1`
footer. A synthetic positive/adversarial unit test refuses missing
images, wrong counts, fake UI, missing second-battle record and unchanged
gameplay. The audit does not infer physical Switch hardware or validate
the PS1 battle database.

The eight-guest workflow must pass on its **exact source commit**
before the ZL panel is considered emulator-verified. Stage 355 source
and earlier NeXium evidence are unchanged while that check runs.

## Stage 357 — ROM-free victory reward prototype

A validated **Victory** followed by the **first B exit** now credits
a deterministic placeholder reward of **8 EXP and 12 Gella** to the
volatile `FieldBattleSession::rewards` account. These amounts are
synthetic design parameters, **not original PlayStation reward tables**.
No payout occurs on `Defeat`, early `Retreat`, invalid input/state,
held B, or reopening a new battle. The payout reported on close is the
**actual** added amount after saturating `uint32_t` arithmetic, never
an unbounded nominal value.

The normal field game image remains unchanged. Explicitly **holding ZL**
displays a read-only balance in the existing battle-results panel;
releasing ZL restores identical field pixels. No changes are made to
the original 40-byte field save, clue journal, quicksave or emulator
R/ZR opt-in input routes. The earned EXP/Gella remain **session-only**
until a separate, versioned battle-progress save format is implemented.

`wa_field_battle_rewards_tests` exercises genuine two-hit terminal
wins, two successive wins, defeat and retreat with no rewards,
exactly-once B close, saturated balances reporting actual payout,
corrupt battle refusal, original pixel parity and an opt-in panel
without state mutation. This feature requires its own Host Core
and Switch NRO CI checks before claiming to work in the emulator.

## Stage 358 — separate versioned battle progress record, codec only

An independent, fixed-length 36-byte `WABR` binary record v1
holds the session's three terminal outcome counters, last outcome,
accumulated synthetic EXP and Gella, and CRC32. It does **not**
modify or replace the 40-byte `WAFS` field/save format. The format
uses explicit little-endian fields, reserved-zero padding and an exact
length/CRC check; it never serializes native C++ struct padding.
Decoding a corrupt, wrong-version, truncated, oversized or contradictory
record never changes live `BattleProgress`.

`wa_field_battle_record_tests` covers a clean empty record, an
authentic battle-session victory and payout, byte-order checks, maximum
32-bit counters, invalid last-phase relationships, changed CRC, wrong
magic/version, reserved bytes and atomic failure. This is a **codec
only**: no actual SD card read/write yet. A separate transactional
disk-save layer will be required before suggesting that wins or EXP
survive restarting the game. The existing exploration saves continue
to function independently.

## Stage 359 — independently versioned battle progress journal

The Switch prototype now loads battle history and EXP/Gella at startup
from a **separate battle-progress.a / battle-progress.b** two-generation
journal under `sdmc:/switch/wild_arms_field/`. On the first validated
B-close of each battle, the game attempts to persist the updated
volatile progress. Missing, unreadable or corrupt data never changes
the live counters; unavailable SD storage remains nonfatal. Ordinary
field quicksaves continue to use `field-save.a/.b` and unchanged
40-byte WAFS payloads.

The battle journal is a fixed **52-byte WABJ** wrapper consisting of
magic, 64-bit little-endian generation, independent 36-byte WABR v1
progress record, and another CRC32. Storage writes to the *older*
slot's `.tmp`, flushes+fsyncs, reopens and byte-validates the
temporary file, then replaces only the older slot and verifies
published bytes. The newest fully validated generation is never
overwritten in the normal write path. Readers ignore orphaned
temporary files and recover the latest fully validated copy after
a torn write, damaged peer or interrupted rename. A tie with unequal
payloads fails as corrupt; a generation counter at UINT64_MAX fails
closed instead of wrapping.

`wa_field_battle_file_tests` exercises two generations, restart
recovery, partial/fully synced uncommitted temp, interruption after
removing the older slot or after publish, damaged newest fallback and
repair, both slots corrupt, truncated/extra bytes, invalid balances,
sequence exhaustion and unchanged separate field data.

**Limits:** CRC32 is a corruption check, not cryptographic
authentication; POSIX-like fflush/fsync/rename cannot guarantee actual
SD/FAT power-loss durability without hardware/firmware validation.
This is an asset-free synthetic battle prototype, not original PS1
save data. The new file I/O requires separate exact-head CI and a real
NeXium restart/reload test before claiming persistence is verified
on a Switch emulator.

## Stage 360 — two independent real NeXium process battle-save replay

A ninth and tenth NeXium guest, each a **new process**, now run in
one isolated `NEXIUM_DATA_ROOT`, separate from all original field
saves. The first guest confirms initial `EXITS 0` via real held-ZL
pixels, performs R→B retreat, and stops. CI requires an actual 52-byte
`battle-progress.a` guest SDMC journal and copies the entire first
committed record as evidence. The tenth guest boots from the **same
SDMC directory**, uses ZL to show **EXITS 1 LAST RETREAT** after launch
without any new battle, releases ZL and verifies original field pixels,
then performs another R→B retreat to commit
`battle-progress.b` generation 2. This script refuses unexpected
creation of unrelated `field-save.a/.b`.

The independent `audit_nexium_battle_persistence.py` examines six
actual 1600×900 screenshots and all three observed guest journal files.
It decodes little-endian WABJ/WABR records, independently validates
both CRC32 checksums, exact sizes, reserved bytes, last-outcome
relationships, generations 1→2, retreat counter 1→2, zero placeholder
rewards, **preservation of old generation bytes**, and six game-frame
observations. No in-memory test state is trusted. An adversarial
Python unit suite rejects corruption, missing or counterfeit evidence.

This is **experimental NeXium filesystem evidence**, not an actual
Switch hardware power-cut durability guarantee. The ninth/tenth
guests and exact-head Host Core/NRO need to complete successfully
before restart persistence is considered confirmed.
