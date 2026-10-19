# Stage 270 — libnx software-framebuffer field prototype

This new `switch/` target adapts the synthetic gameplay core from stages
265–269 into a native Nintendo Switch **homebrew NRO** build target, isolated
from host CMake. The repository does **not** include a compiled NRO by default.

The frontend uses the current libnx `NWindow` + `Framebuffer` API at
1280×720 in double-buffered linear RGBA8 mode, and the `PadState` HID API.
An original 11×7 ASCII test map is shown as coloured 64×64 rectangles,
including walls, floor, event and exit tiles. A red square marks the
character and a small dark rectangle indicates facing. A narrow top stripe
turns amber when an event/exit needs acknowledgement; pressing **A**
acknowledges it. Use **D-pad** or **left stick** to move, and **+** to exit.

Each update samples the hardware counter and passes a bounded integer
millisecond delta through `advance_pad_frame`. The Switch stick's +Y-up
axis is inverted for the core's +Y-down field convention. Time elapsed
during long applet pauses is intentionally clamped to 1000 ms instead of
letting the character jump many steps after resume.

## Build

Install devkitPro's `switch-dev` toolchain and ensure `DEVKITPRO` points to
its installation. Then run:

```sh
make -C switch
```

The output should be `switch/wild_arms_field.nro` after a successful build.
The independent GitHub Actions workflow `Switch field prototype` attempts
the same build inside `devkitpro/devkita64` and publishes the NRO only if it
passes. Do not treat presence of a workflow or source code as proof that a
binary was built or ran on hardware.

## Constraints

- No original Wild Arms sprites, maps, CD/BIOS, music, scripts, or other
  copyrighted game assets are used or uploaded.
- This tests an **original synthetic** walkable map, not the original game's
  field, battle, event or camera engine.
- Gameplay is tile-by-tile, not pixel-interpolated walking.
- There is no original PS1 asset loader, original-compatible save format,
  or battle system. Later stages added synthetic NeXium field captures and
  experimental SD-backed field saves, but no physical Switch validation.
- The standalone `switch/source/field_core.cpp` includes the canonical
  `src/field.cpp` once, avoiding a divergent field logic implementation.
- CTest remains the authoritative host-level correctness check; the NRO
  build workflow proves cross-compilation only when green.

## Next verification

Verify native compilation in CI; inspect actual gameplay in a Switch
homebrew-compatible emulator or personal Switch; compare key orientation,
frame pacing, display output, suspend/resume, and event acknowledgement.

## Stage 291 — volatile manual quicksave

In **manual** field mode, press **Y** to remember the current complete
world/player/event/controller state in an in-memory slot, then **− (Minus)**
to restore it. Saving or restoring consumes one update without moving or
acknowledging a pending event. An empty slot does nothing, and a malformed
snapshot is rejected before replacing the live state. Both controls are
ignored during scripted autoplay (X); after B resets manual exploration,
the in-memory checkpoint remains available.

This is **not** a persistent game save. The slot is lost when the NRO exits
or the console closes the process. No Wild Arms original save data or game
files are read/written. The five established NeXium autoplay reference
frames and their pixel parity contract are deliberately unchanged.

## Stage 293 — versioned field save record (portable host codec)

The host/Switch-neutral \`include/field_save_codec.hpp\` introduces a fixed
40-byte v1 record for the *synthetic* manual field state. It encodes map
identity, location, facing, movement counter, movement-clock state, active
trigger and confirm-button decoder using fixed-width little-endian fields.
An explicit 32-bit CRC detects accidental byte corruption; an independent
64-bit world fingerprint rejects saves from incompatible synthetic maps.
Reserved fields, unsupported versions, malformed coordinates/clock/pending
events and truncated or extended records are rejected **without modifying
the live player or the previous destination state**. It uses no proprietary
Wild Arms save data.

This is a **serialization library only**. Stage 293 does **not** write to
the Nintendo Switch SD card, add persistence between process launches, or
change Y/Minus quicksave behavior. These require a future platform-specific
file adapter with atomic replacement and failure recovery. The synthetic
five-scene reference PNGs, known NeXium guest visuals and valid NRO layout
remain unchanged.

\`wa_field_save_codec_tests\` is included in Host/Matrix CTest coverage.

## Stage 294 — experimental SD save integration

The Nintendo Switch homebrew build now attempts an SDMC mount with
`fsdevMountSdmc` (reuses an existing `sdmc` device), and creates its own
`sdmc:/switch/wild_arms_field/` directory. The synthetic game uses two
generational files, `field-save.a` and `field-save.b`. **Y** still creates
its normal in-RAM snapshot; after the gameplay frame succeeds, it also
writes a generation to SD when the directory is accessible. The writer
generates a verified 56-byte record containing the Stage-293 40-byte
versioned state, and updates the *other* slot using a temporary file,
flush, `fsync`, close, read-back verification, and rename. It does not
unlink the currently newest validated save. **Minus** uses the same
original RAM quickload; if RAM has no snapshot (e.g. a new app launch),
it imports the most recent validated SD generation before drawing.
A corrupt latest slot may fall back to a valid older generation.

**Important limitations:** SDMC may be unavailable (notably in
emulators). If it is unavailable or a file write fails, RAM quicksave
continues but there is an explicit transient RAM-only or SD-error screen
indicator (added at Stage 295), but this does not prove file-system
power-loss durability. There is no claim of full SD FAT/exFAT power-loss atomicity,
durable directory metadata, concurrent-process writer protection, or
tested persistence across two native Switch hardware sessions. The
journal provides recoverable independent generations in normal tested
file-system failure scenarios, not a guarantee for sudden hardware
power loss. No original game content is written. The existing five
autoplay and eight NeXium manual screenshots are unchanged.

Host `wa_field_save_file_tests` exercises normal load, journal generations,
corrupt-latest fallback, stale temporary files, blocked replacement,
world mismatches, and generation exhaustion. The Switch NRO must be
cross-compiled separately and manual SD persistence must be verified
on an actual console before being called hardware-confirmed.

## Stage 295 — storage outcomes shown inside the game

The Switch NRO now renders a small 900 ms **front-end-only** status plaque
in the upper-right margin, with independently generated 5×7 pixel
lettering. This plaque never changes the `advance_field_runtime`
logic, the five canonical host captures, or the field map.

- **SD SAVED** (green): a fully checked journal write returned success
- **RAM ONLY** (amber): SDMC was unavailable; the Y quicksave is in RAM
- **SD ERROR** (red): attempted SD read/write failed
- **SD LOADED** (cyan): first Minus restored a verified SD record
- **RAM LOADED** (blue): Minus restored the existing RAM snapshot
- **BAD SAVE** (red): persisted generations are invalid
- **NO SAVE** (gray): no RAM or usable persistent record is present

This indication reports **only the operation observed at runtime**;
it does not certify sudden-power-loss durability or an actual
Nintendo Switch hardware save. It disappears during autoplay so all
five canonical reference scenes remain unaffected. Host tests assert
all outcome colours, text drawing bounds, and deterministic expiry.
NeXium manual screenshot capture now waits for the transient indicator
to disappear before comparing the original scene pixels, and separate
transient captures are kept for UI validation.

### Stage 295: stronger guest plaque pixel parity

The real NeXium feedback auditor now matches the *entire* projected
storage indicator rectangle (excluding only a three-desktop-pixel
edge margin) against an independently defined rasterization of the
native C++ plaque and its 5×7 lettering. It reports the number of
observed RGB mismatches and fails for even one changed visible pixel,
including cases where the badge colour is correct but the words are
wrong. This check is separate from the established five-scene,
4,112,580-pixel gameplay parity audit.

## Stage 296 — verified interrupted-write recovery windows

The generational journal now includes an **opt-in, test-only**
`JournalInterruption` fault injector. Normal Switch calls always use
`None`; no deliberate failures are enabled in the compiled NRO.
Host CTest simulates interruption after (1) a partial 11-byte temporary
write, (2) temporary flush/fsync/close, (3) temporary read-back
verification, (4) removal of the previous older slot, and (5) final
rename into the destination slot. Each case starts with a known-good
generation 2, attempts generation 3, and verifies generation 2 is still
readable byte-for-byte. Before rename, no temporary file is accepted
as a committed save. After rename, the complete generation 3 may
correctly load even if the process never reported success. A fresh
write after each interruption must advance the journal and recover
normal loading. Separate tests cover interruption of the very first
save, with no prior committed generations. The writer now also removes
the temporary file if a normal rename fails.

**These checks use the host filesystem and deterministic stops between
operations.** They do not emulate a real hardware power cut during
the middle of an SD write, simulate FAT/exFAT metadata corruption, prove
`fsync`/rename durability on the physical Switch, or protect against
concurrent writing processes. As before, the synthetic five-scene
field visuals and on-screen notification colours are untouched.

## Stage 297 — independent process SD-backed event reload

A separate experimental NeXium guest process now launches after the
first NeXium process has completed and after it saved an **event** via
Switch Y with the visible `SD SAVED` indication. Both processes use
the same emulator data root, but each launches the NRO anew with
`FieldRuntime` and the in-RAM quicksave slot initially empty.
The first screenshot of the second run must exactly match the native
host's fresh manual start scene. The second process then receives
only Switch Minus; its transient notice must be pixel-identical to
`SD LOADED` (not `RAM LOADED`), and its final frame must exactly
match the first process's previously saved pending event scene and
the same-commit host reference. Distinct runner process IDs and the
first run's completed wait are written into an auditable manifest.
The dedicated audit is fail-closed for missing screenshots, wrong
PID identity, missing first-process SD-save evidence, mismatched
host references, or even one mismatched storage plaque RGB pixel.

Host CTest also creates **two real OS processes**: the first writes
the 56-byte journal, and the next starts with empty memory, imports
the pending event, and acknowledges it. Additional subprocess tests
reject a stale incomplete temporary file and corrupted committed
record without changing live state.

The NeXium guest proof is still an experimental emulated SD mount.
It does not prove physical Nintendo Switch SD hardware durability,
abrupt power-cut safety, or proprietary original Wild Arms saves.

## Stage 298 — warn on degraded two-generation SD journal

A successful SD load no longer always reports `SD LOADED`. The new
`load_field_save_file_detailed` adapter returns both the unchanged
`Loaded` status and a `degraded` flag when **one journal generation
was invalid but the other was fully verified**. In that case the game
restores the intact state and briefly shows the amber **SD WARN**
message, advising that the redundant backup was damaged. It does not
claim which generation failed unless its integrity and sequence data
were independently validated; the warning applies even if the damaged
slot is older than the loaded slot.

The original public `load_field_save_file` continues to return the
same `FileSaveStatus` values, and the journal layout and two-slot
writer are unchanged. A missing older generation (normal after the
first ever save) does not count as corruption. No valid generation
still returns a failure without modifying the world; an I/O error
remains fail-closed. A subsequent normal save can replace the
damaged slot and restore the two-generation health state.

Host tests cover one valid slot, both valid slots, damaged newest,
damaged oldest, successful repair and both-damaged refusal, alongside
UI status mapping and the new letter W glyph. Normal uncorrupted
NeXium screenshot parity remains identical.

## Stage 299 — real NeXium emulated SD corruption and third-process fallback

After the already proven two successful NeXium guest processes, the
experimental workflow now inspects the emulator's **isolated**
`$NEXIUM_DATA_ROOT/sdmc/switch/wild_arms_field/field-save.{a,b}`
files. Upstream NeXium's `nexium-common/src/paths.rs` and
`nexium-kernel/src/fs_host.rs` map guest `sdmc:/` to this host
directory. The audit refuses to modify unknown or incorrectly
formatted files; it verifies 56-byte `WAJ1` records, generations 1
and 2, CRC-32, and exact byte hashes first. It modifies exactly byte
23 of the *newer* B record without recomputing CRC, leaving A intact.

A **third fresh NeXium process** then imports from the same data root.
Its initial and restored gameplay screenshots must exactly match
the clean area-0 start reference. Its transient status plaque must
be pixel-identical to amber **SD WARN**, not an ordinary healthy
`SD LOADED` and not a same-colour `RAM ONLY`. The audit also
re-reads the host journal: A's original SHA-256 and valid CRC must
remain, while B's expected corrupted SHA-256 and failed CRC must
remain. Every screenshot and manifest is retained as CI evidence.
The scenario is deliberately gated on real guest execution rather
than passing synthetic tests alone.

This is controlled byte damage to **emulated** SDMC files, NOT a
real Switch SD or sudden-loss power test. No user-owned game assets,
ROM images or commercial resources are touched.

## Stage 300 — fifth-process validation after repairing the journal

After the Stage 299 damage/fallback test, a **fourth independent
NeXium process** launches from a clean runtime, presses Minus to
restore the intact generation A, and must show amber `SD WARN`.
It then saves the recovered location with Y, replacing damaged B,
and must display green `SD SAVED` with no gameplay scene change.

A **fifth fresh guest process** starts with no RAM checkpoint and
presses only Minus. It must now show cyan `SD LOADED` (not
`SD WARN`), proving that a healthy journal was republished. The
auditor requires valid generation-1 and generation-2 CRC32 records,
an unchanged SHA-256 for the older A, a new B hash different from
both original and intentionally damaged B, distinct guest process
IDs, and full projected RGB equality for three status plaques and
three gameplay screenshots. The same-commit host references are
verified and the diagnostic files are retained as CI artifacts.

As before, the scope is NeXium's isolated emulated filesystem only,
not Nintendo Switch hardware durability or physical SD power loss.
