# Stage 269 — host-only controller adapter for field exploration

A platform-neutral `PadSample` in `include/field_controls.hpp` maps D-pad
buttons and signed 16-bit stick axes to the existing deterministic
`wa::field::Input`. This adds NO native Switch integration.

- D-pad overrides the stick while **any** D-pad direction is held.
  Opposing D-pad buttons are forwarded as ambiguous input instead of being
  silently resolved. Diagonal stick input is also forwarded as simultaneous
  directions, which `advance_timed` rejects.
- Analog deadzone threshold is inclusive at ±16000; all input arithmetic
  promotes to `int` before comparing, including axis value −32768.
  Stick +Y means *down* by this adapter's field-coordinate convention;
  the future platform frontend must normalize its actual hardware API.
- Confirm is an **edge**, not a level: keeping it held cannot acknowledge
  consecutive events. Event/exit acknowledgement consumes the frame and
  intentionally discards that update's elapsed milliseconds.
- Invalid clock, delta, map and player state reject the entire controller
  update without consuming the confirm edge. No original game assets are used.
- `tests/test_field_controls.cpp` checks axis boundaries, D-pad precedence,
  conflicting input, event and exit acknowledgement, held-confirm behavior,
  invalid state invariants and deterministic controller-to-viewport replay.

Host verification:

```sh
cmake -S . -B build
cmake --build build --target wa_field_controls_tests
ctest --test-dir build -R wa_field_controls_tests --output-on-failure
```

**Limitations:** This is a synthetic host C++20 control layer. It is not a
physical controller driver, a libnx frontend, a Nintendo Switch NRO, a
rendering loop, an emulator verification, or a reconstruction of game logic
from the original disc. Future Switch code must translate HID samples and
clock deltas explicitly and verify axis orientation on the actual backend.
