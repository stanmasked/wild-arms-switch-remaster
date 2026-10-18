# Stage 283 — actual NeXium process smoke attempt

The verified `wild-arms-field-emulator-handoff` bundle from Stage 282
includes a Nintendo Switch homebrew NRO and five synthetic reference
images, but **no NeXium run had yet been observed**.

The separate experimental `NeXium Linux NRO smoke` workflow attempts
to change this. It cross-compiles a fresh NRO at the exact GitHub commit,
then launches the official Linux NeXium nightly in a Linux Xvfb window
with Mesa's software Vulkan driver (lavapipe).

The official Linux nightly archive is an experimental binary download
from `nexium-emu/nexium-nightly`. It is pinned by **SHA-256**; any
upstream change to the rolling nightly fails the checksum check before
executing unverified bytes. CI does not fetch firmware or commercial
assets, and uses only independently invented synthetic test maps.

The workflow stores NeXium stderr/stdout, Vulkan adapter detection,
dynamic library diagnostics and three Xvfb screenshots in
`nexium-experimental-probe-evidence`. Its classifier
`tools/audit_nexium_probe.py` looks for several exact colors from our
field raster in the actual desktop screenshots. A launched process or
open GUI window **does not count** as verified game execution. If no
signature is present the status is explicitly `runtime_not_confirmed`.

The test is deliberately independent from required NRO cross-build CI.
The NeXium step is experimental and may fail on hosted runners due to
Vulkan, GTK, CPU JIT, homebrew HLE or missing display support. It does
not test the five gameplay checkpoints: even a positive visual
signature is only evidence of an initial field rendering. Full
gameplay/controller verification still requires confirmed input and
five real captures compared to the host reference bundle.

The classifier has synthetic PNG unit tests for actual palette
detection, a blank desktop, absence of screenshots and malformed
metadata. These tests alone are not emulator verification.

Official emulator homepage: https://nexium-emu.org/
Official nightly archive: https://github.com/nexium-emu/nexium-nightly/releases

## Initial NeXium attempt — runtime blocker found

The first Linux emulator probe for commit `75013284` **did run the
CI setup and downloaded the verified official NeXium archive**, but
NeXium exited before loading the NRO:

```
/lib/x86_64-linux-gnu/libm.so.6: version 'GLIBC_2.43' not found
```

GitHub Actions run `39166644123` captured three black Xvfb screenshots.
`evidence.json` states `runtime_not_confirmed` and all synthetic
field palette counts are zero. The workflow conclusion was green
**only because the emulator experiment was marked continue-on-error**,
not because the game ran.

The correction switches only this experimental job to `fedora:44`,
which provides GNU libc 2.43, retains the exact pinned NeXium archive,
and records the emulator process exit code even on failure. Subsequent
results must still be checked for an actual guest framebuffer.

## Fedora 44 follow-up — missing XKB X11 bridge

The Fedora 44 attempt `39167127996` started the Linux binary
past GLIBC dynamic loading, but the GUI panicked before drawing:

```
Library libxkbcommon-x11.so could not be loaded
```

The reported process exit code was 101, all three Xvfb screenshots
remained blank, and `runtime_not_confirmed` was correctly recorded.
The correction installs Fedora package `libxkbcommon-x11` and asserts
the shared library is visible to the dynamic linker before launching
NeXium. No NRO runtime claim is made until actual guest pixels appear.

## Stage 284 — NeXium splash visible, guest field not yet rendered

Run `39167371006` successfully launched the **NeXium GUI** after the
Fedora/XKB repairs. Its screenshots show NeXium's animated gradient-edged
splash window, **not our synthetic Wild Arms field**. The pixel
classifier correctly reported `runtime_not_confirmed`: all field
palette and player pixel counts were zero. The process exit code was 137
after the workflow's 75-second `timeout` and SIGKILL grace period.
That exit code alone cannot distinguish a forced timeout kill from an
out-of-memory kill, so no OOM conclusion is justified.

The next experiment increases the bounded guest-run budget to 130 seconds,
records `ps` CPU/RSS samples and cgroup memory, activates the X11
window using `xdotool windowfocus` instead of the unsupported EWMH
`windowactivate`, and captures five timestamped desktop screenshots.

The experimental NeXium workflow now **fails** if field pixels never
appear, rather than presenting a misleading green workflow when
`continue-on-error` allowed a GUI-only attempt to pass. Artifacts and
summary are uploaded on failure. This workflow remains separate from
regular project CI and uses no proprietary firmware or game dumps.

## Stage 285 — host frontend vs guest startup isolation

The Stage-284 extended NeXium probe `39168069968` failed the actual
guest-pixel classifier: five virtual display captures remained at the
NeXium splash, with no Wild Arms synthetic tile colours. The process
consumed roughly 62% of one CPU core and stayed at 168 MB RSS for
130 seconds; cgroup memory stayed near 1.46 GB rather than growing.
Exit code 137 followed `timeout` signal escalation, **not independently
verified OOM**.

The next experimental run starts NeXium **without** an NRO after the
failed/successful guest launch, on the same Fedora 44 Mesa Vulkan/Xvfb
environment but with an isolated empty data directory. It captures the
control window and compares RGB channels to the last guest-attempt
screenshot using `tools/audit_nexium_launch_control.py`. The report
records the fraction of desktop RGB channels differing by at most 16.
A high similarity only suggests that both runs show the same GUI
state; it cannot prove guest execution or pinpoint a CPU/JIT bug.

The no-NRO control test is intentionally nonblocking to retain logs on
failure, while the main guest-pixel verification remains a strict CI gate.
Unit tests use invented desktop images, not an actual emulator.

## Stage 286 — capture the actual NeXium host session logs

NeXium uses `nexium_common::file_logger::FileLogger` and writes the
internal `Auto-loaded NRO`, `Boot: NRO`, `Failed to load NRO` and
GPU/loader messages to
`$NEXIUM_DATA_ROOT/logs/nexium-YYYYMMDD-HHMMSS.log`.
Standard-output redirection captured primarily unrelated ALSA warnings
and omitted these diagnostics on every earlier run.

The experiment now exports the latest bounded (2 MB) log from **both**
the NRO launch and the no-NRO control run, and uses a standard-library
host analyzer to identify whether the emulator merely started its GUI,
attempted loading, accepted the file, or logged a failure. Missing files
are explicitly recorded rather than silently treated as empty success.
Neither a successful loader message nor a green build proves a frame
was rendered; actual screenshot evidence remains mandatory.

## Stage 286 — real guest NRO fails upstream NeXium 16-byte offset check

Detailed `NEXIUM_DATA_ROOT/logs` artifact from the failed guest/control
attempt `39169208671` finally exposed the immediate error:

`[nexium_runner::boot] Boot failed: Data segment out of bounds`

This is caused by a NeXium loader logic defect for normally wrapped
homebrew files: `nexium-loader/src/nro.rs` detects `NRO0` at
`input[16..20]`, then slices the input from byte 16, but compares
unchanged segment offsets against this **shortened** slice. In the
original asset-free NRO, `.data` ends exactly at byte 151,552,
which is the complete and valid file length. NeXium instead compares
that valid endpoint to 151,536 (= 151,552 - 16), reporting an apparent
16-byte overrun. Our canonical NRO0 checker correctly accepts the file.

This commit intentionally **does not modify the valid standard NRO**.
Instead the separate experimental NeXium smoke workflow creates a clearly
named NON-STANDARD diagnostic copy, appending exactly 16 zero bytes
without replacing or publishing it as a valid homebrew artifact. The
probe is only for isolating NeXium's loader bounds check and can still
fail at later stages because loader offsets remain inconsistent.
The manifest records original/probe SHA-256, added bytes and explicitly
marks the probe `probe_is_valid_standard_nro: false` and
`guest_execution_verified: false`. Unit tests guarantee the source
binary is unmodified and reject reuse or other file shapes.

A long-term fix belongs in NeXium's own loader code; the emulator-only
padding is NOT an acceptable change to the production NRO.

## Stage 288 — first real guest rendering and corrected X key capture

Commit `78f0408c` and NeXium experimental workflow `39170237497`
produced the first actual guest field framebuffer from the synthetic
game in NeXium, on Mesa llvmpipe. The internal emulator log confirms
`FIRST NON-BLACK FRAME`, `Starting emulation loop`, and thousands of
guest presentations; five screenshots contain expected wall/floor/exit
and player pixels. The emulator used a clearly nonstandard padded copy
only to isolate the upstream 16-byte NRO bounds-check bug. The
valid Nintendo Switch NRO was not changed.

A visual comparison of the five game regions found them identical:
autoplay had NOT been verified. The upstream official NeXium controller
defaults in `nexium-gui/src/controller_config.rs` map
Switch **X** to physical keyboard **V**, while physical X maps Switch
**B**. The previous smoke sent the wrong key, and waited 20 seconds
before its first screenshot, around the entire round-trip duration.

The corrected experimental workflow sends a deliberate V key-down and
key-up, samples at 5, 10, 17 and 29 seconds from the press, and uses a
new host desktop screenshot comparator to distinguish true changes in
the central game field from fluctuating FPS overlays. The comparator's
ROI is specific to Xvfb 1600x900 and must not be used for arbitrary
display sizes. No result is called successful full checkpoint parity:
even a visible change establishes only a possible response to input,
not all 23 scripted actions. The NRO padding remains diagnostic only.

## Stage 288 — visual event and round-trip verification

NeXium run `39171302136` passed with real guest rendering and
visible movement after correct host key **V** (Switch X). The game
ROI changed by 2,757 pixels at +5 and +10 seconds; screenshots
at +17 and +29 seconds matched the initial game ROI exactly.
The intermediate screenshots had the yellow event status strip and
the initial/return screenshots had the green normal-state strip.

The strict screenshot audit now requires all three observations:
visible game ROI movement, yellow event status, and byte-identical
returned ROI. Its test fixtures cover positive and false-positive
scenarios. These results do not establish all five exact host
checkpoint images or authenticate keyboard event delivery.

## Stage 289 — five in-order NeXium screenshots vs same-commit host

Experimental CI builds **five canonical 1280x720 host reference PNGs**
and the Switch homebrew NRO from the exact same git revision. The NeXium
job downloads both artifacts and launches ONLY the clearly labeled,
nonstandard +16-byte emulator compatibility probe. The genuine NRO
continues to be unchanged and valid for actual Switch use.

After sending host keyboard V (mapped to Switch X), the workflow samples
80 actual Xvfb desktop screenshots about every 220ms plus PNG export
time. `tools/audit_nexium_checkpoints.py` verifies host reference PNG
and decoded-RGB SHA-256 checksums and selects images in the correct
scene order:

0. Area 0 start (initial before X)
1. Area 0 event (yellow status; player at x=4,y=1)
2. Area 0 exit (yellow status; player at x=6,y=5)
3. Area 1 start (blue status, different terrain and player)
4. Area 0 return (green status; player returns to x=1,y=1)

The method projects 77 terrain samples, expected player colour/centre
and status colours from each canonical host reference into the fixed
NeXium 1600x900 desktop layout. It excludes FPS/UI overlays and
requires exact screen ROI equality between first and last scenes.
It saves original screenshots under `verified-checkpoints/` with a
SHA-256 manifest. Missing scenes fail closed, with all raw timeline PNGs
and diagnostics still uploaded for further debugging.

**This is a structural sample comparison, not complete pixel-by-pixel
1280x720 parity.** The NeXium frontend rescales the original framebuffer
into an Xvfb desktop, so an exact full-frame comparator requires a
separate proven inverse scaling/capture API. The five checks also do not
prove exact timings for every one of the 23 logical scenario steps.
No original Wild Arms assets or firmware are used.

## Stage 290 — exact visible RGB matching for five real emulator scenes

Experimental GitHub Actions `39173021610` **succeeded**: it captured
80 screenshots and independently selected all five in-order NeXium
checkpoints, each with 77/77 matching terrain colour samples, matching
player position/colour and status bar. This demonstrates the whole
scripted round trip, not only a generic frame change.

On the downloadable actual NeXium Xvfb screenshots, an additional
comparison with the **same-commit** host reference PNGs found a precise
nearest-neighbour projection:

- Native 1280×720 host image scales to 1234×694 in the desktop.
- Game viewport is Xvfb rectangle x=23..1256, y=0..693.
- The NeXium-host performance overlay obscures a 220×154 region in
  the upper-left corner of that viewport. It is **not guest graphics**.
- Across 5 checkpoints, excluding the overlay, **4,112,580 visible
  projected game pixels matched exactly, zero mismatches**.
- The excluded 169,400 pixels lie outside the active tiled map. The
  source 1280×720 GPU framebuffer was **not directly extracted**.

The new `tools/audit_nexium_pixel_parity.py` verifies that exact RGB
correspondence in CI, after the existing ordered checkpoint selector.
It fails for even one changed visible RGB pixel, checks all same-commit
reference hashes via the existing reference verifier, and records a
per-scene full SHA-256 evidence report. The test excludes only the fixed
NeXium on-screen performance HUD, never changes the original NRO and
never claims direct native framebuffer capture. This geometry is
specific to the verified 1600×900 Xvfb + 1280×720 NeXium view; if the
window layout or scaling changes, the audit should fail until a new
layout is independently established.
