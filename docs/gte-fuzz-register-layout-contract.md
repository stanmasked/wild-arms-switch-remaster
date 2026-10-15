# Independent register-layout contract for gte-fuzz RTPS captures

Verified the register indices and packed signed 16-bit halfword order in `tools/import_gte_fuzz_rtps.py` against [psx-spx GTE register specifications](https://psx-spx.consoledev.net/geometrytransformationenginegte/).

The rotation matrix input is extracted from control registers 32–36 with the following row-major halfword order:

- 32 low/high: RT11, RT12.
- 33 low/high: RT13, RT21.
- 34 low/high: RT22, RT23.
- 35 low/high: RT31, RT32.
- 36 low: RT33.

Other inputs are translation TRX/TRY/TRZ in 37–39; vertex VX0/VY0 packed in 0 and VZ0 in 1; H (58), OFX/OFY (56/57), DQA/DQB (59/60), sf and lm from the GTE command.

Expected results read IR0–IR3 (data 8–11), SXY2 (14), SZ3 (19), MAC0–3 (24–27), and FLAG (control 63).

Added `tests/test_gte_fuzz_register_mapping.py` with a fully differentiated *synthetic* 64-input/64-output RTPS capture to check all 22 imported input fields and all 11 output registers, including extreme signed 16-/32-bit values and packed high/low halves. Two additional tests verify sf/lm interpretation and negative signed boundaries.

## Confirmed verification

The 3 new Python tests passed. A fresh local CMake configure/build and CTest run passed **23/23 suites**, including the new named suite `wa_gte_fuzz_register_mapping`.

This validates the **register-to-JSON mapping**, not hardware arithmetic or captures. No actual PS1 hardware output has been imported and no independently authenticated benchmark run is claimed. The project remains host-side C++ analysis code, not a playable Nintendo Switch Wild Arms port.

Reproduce using `cmake -S . -B build && cmake --build build -j4 && ctest --test-dir build --output-on-failure`.
