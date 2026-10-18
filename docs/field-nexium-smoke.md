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
