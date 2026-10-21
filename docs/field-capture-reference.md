# Stage 274 — deterministic host reference screenshots

A successful NRO cross-build from Stage 273 does not demonstrate actual
emulator execution. This stage supplies a **separate host reference** for a
future emulator comparison without mislabeling it as a real Switch capture.

The `wa_field_capture` C++20 executable walks the same original synthetic
11×7 maps used in the libnx frontend. It exercises:
1. Initial area 0 view.
2. Entry onto an event tile (paused until A).
3. Exit tile in area 0 (paused until a new A press).
4. Arrival at area 1.
5. Completion of area 1 and return to area 0.

The replay asserts 20 successful moves, two real area changes and valid
event/exit pauses; each frame comes from the same `draw_field_pixels`
implementation that the Switch NRO links.

GitHub Actions runs the host replay twice and requires **byte-for-byte
identical** raw RGB pixels for every named scene. A Python standard-library
audit checks exact frame dimensions, two representative bar/background
pixel colours per scene, distinct intermediate scenes, exact initial/return image equality\nand exports lossless PNGs,
with a manifest containing full RGB and PNG SHA-256 digests.

View outputs from the GitHub Actions workflow
`Field capture reference (host, no emulator)`. They are explicitly
host-rendered reference images, **not proof that a Switch emulator,
Horizon framebuffer or HID event stream has executed successfully**.

Local verification:

```sh
cmake -S . -B build
cmake --build build --target wa_field_capture
ctest --test-dir build -R wa_field_capture_replay --output-on-failure
./build/wa_field_capture capture-one
./build/wa_field_capture capture-two
python3 tools/audit_field_capture.py capture-one capture-two --output field-references
```

## Future actual emulator verification

Launch the CI-produced `wild_arms_field.nro` with an emulator that
supports libnx homebrew and framebuffer rendering. Capture the initial
map, event pause, exit pause and second map from the emulator itself.
Record the emulator version, launch command, operating system, renderer,
controller state, elapsed time and source commit. Compare observed
positions, colours, pause/acknowledgement and movement with these host
references. Do **not** attribute a host PNG to the emulator.

The current environment has no installed Switch emulator or Vulkan
rendering session; no emulator screenshots or real-device results were
produced in this stage. No original Wild Arms game assets are included.
