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
