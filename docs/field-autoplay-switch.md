# Stage 275 — deterministic NRO autoplay and host capture parity

The successful Stage-274 reference workflow published five synthetic PNGs.
The compiled Nintendo Switch NRO has not yet been run in an emulator.

A single nine-segment command trace in `include/field_scenario.hpp` now
drives both `wa_field_capture` and the Switch frontend. It comprises
23 160-ms logical ticks, 20 successful moves, one event acknowledgement,
two bidirectional area transitions, and five validated checkpoints.

**Controls in Switch NRO**: press X to start or restart the scripted route;
the starting screen and each subsequent checkpoint are held for about
2.5 seconds, with about 350 ms between intervening actions. The final
checkpoint remains on screen. Press B to return to manual control,
or + to exit. Manual D-pad, left stick and A are unchanged.

Host unit test `wa_field_scenario_tests` validates the five checkpoints,
two consistent replays, byte-for-byte first/last framebuffer equality,
and fail-closed handling of modified map or spawn point. The host
PNG capture uses the same scenario instead of separate ad-hoc commands.

These test images are host references, not actual emulator screenshots.
Next: run the NRO in NeXium or another libnx-compatible emulator, press X,
capture the five checkpoints, and compare the results to the published
host PNG reference after recording source SHA, emulator build and
graphics backend. No original Wild Arms content is included.

To check locally:

```sh
cmake -S . -B build
cmake --build build --target wa_field_scenario_tests wa_field_capture
ctest --test-dir build -R 'wa_field_(scenario_tests|capture_replay)' --output-on-failure
make -C switch
```
