# Experimental host perspective projection

Implemented `include/gte_projection.hpp` as **a portable approximation**, not a PlayStation GTE RTPS implementation.

The reference accepts integer coordinates, a depth value and screen offsets, computes a fixed-point Q16 approximation to `min(H / max(clamp(z, 0, 65535), 1), 2)`, and reports depth/ratio/screen saturation through **host-only diagnostic flags**, which are **not** the hardware GTE `FLAG` bitfield. Signed multiplication/division uses defined 64-bit integer operations with C++ division truncating toward zero. Output screen coordinates are clamped to -1024..1023 and packed as SXY.

The independent CMake smoke project built and passed `wa_gte_projection_tests` (one CTest test suite). The main repository CMakeLists now registers the same test, but the full repository CI result is **not yet verified**.

## Important exclusions

- Exact PlayStation GTE division algorithm and rounding
- RTPS MAC accumulator widths and overflow behavior
- GTE status bits and per-stage saturation
- Perspective output using PS1 OFX/OFY fixed-point semantics and register FIFO states
- Integration with a full native renderer or Nintendo Switch executable

Next: obtain hardware-level RTPS reference vectors from a trustworthy GTE test suite/emulator or verified original runs, and compare the host implementation before claiming compatibility.
