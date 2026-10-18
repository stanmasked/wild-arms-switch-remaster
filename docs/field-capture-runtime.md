# Stage 280 — capture through the real host/Switch runtime

Stage 279 passed all five GitHub Actions workflows and produced an NRO
cross-build plus five synthetic host-reference PNG images. Actual emulator
execution has **not** been observed.

The `wa_field_capture` host executable now creates its PNG reference
frames by calling `advance_field_runtime` — the same full entry point that
the NRO invokes. It feeds a 19.2MHz monotonic counter, presses X at
tick zero to start autoplay, and advances up to 100 simulated frames
at one-second intervals to make checkpoint transitions deterministic.

The captured surfaces therefore traverse the same path as the native
software framebuffer:

monotonic clock → fractional milliseconds → autoplay pacing →
scenario/world → viewport → 1280×720 RGBA8888 raster → PNG.

For each checkpoint, the executable independently reconstructs the view
and raster from the world state, and requires **byte-for-byte identical
pixels**. It also advances a separate logical scenario oracle, checking
the exact 23 gameplay ticks, two transitions, 20 successful moves,
frame checkpoints and the frozen final frame.

Two independent executions are compared by
`tools/audit_field_capture.py`, as before. Existing scene filenames,
pixel colours and output PNG schema remain unchanged. Any mismatch
fails the GitHub Actions job rather than silently changing the baseline.

No game assets, BIOS/ROM data, or privileged emulator services are used.
This test is a host simulation of the same portable code and **does not
prove NeXium has launched an NRO**.

To run:

```sh
cmake -S . -B build
cmake --build build --target wa_field_capture wa_field_runtime_tests
ctest --test-dir build -R '^wa_field_(capture_replay|runtime_tests)$' --output-on-failure
./build/wa_field_capture capture-one
./build/wa_field_capture capture-two
python3 tools/audit_field_capture.py capture-one capture-two --output field-references
```
