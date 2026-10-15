# Stateful RTPS SZ and SXY FIFO reference

The current host GTE reference models register values for one RTPS invocation but previously did not preserve the FIFO registers between consecutive commands.

PlayStation GTE RTPS rotates two FIFOs:
- Depth: `SZ0 <- SZ1`, `SZ1 <- SZ2`, `SZ2 <- SZ3`, `SZ3 <- transformed depth`.
- Screen: `SXY0 <- SXY1`, `SXY1 <- SXY2`, `SXY2 <- newly projected coordinates`.

Added `include/gte_rtps_fifo.hpp` with `RtpsFifoState`, a pure `push_rtps_fifo()` state transition and `rtps_fifo_reference()`, which combines the existing `rtps_ir0_reference()` model with FIFO state maintenance without modifying the earlier stateless reference.

`tests/test_gte_rtps_fifo.cpp` checks seeded initial registers, exact ordering after successive pushes, unchanged initial state, two consecutive ordinary RTPS operations, and clipping a negative depth to SZ3=0. It is registered as the **26th** test target in root `CMakeLists.txt`.

## Verification actually performed

Built a separate C++20 CMake test project with the relevant host headers and compiled `test_gte_rtps_fifo.cpp`. CTest: **1/1 passed**. Source and test were committed to GitHub. **A fresh complete repository build with 26 CTest targets has not yet been run**, and GitHub Actions status has not been verified for this change.

This is a register-order/state model, not a proof of cycle-accurate or complete GTE. Original proprietary Wild Arms assets were not uploaded. No playable Nintendo Switch binary has been produced.

Relevant independent source: [PCSX ReARMed GTE](https://github.com/notaz/pcsx_rearmed/blob/master/libpcsxcore/gte.c).