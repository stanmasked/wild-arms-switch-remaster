# Experimental RTPS composition using UNR division

The new `include/gte_rtps_unr_reference.hpp` composes existing `rotate_translate()` with `project_unr_reference()`, and preserves the helper-style `SZ3 >> 2` return. Unlike `rtps_reference()`, it uses the GTE-inspired unsigned Newton–Raphson divider instead of normal integer division.

## Confirmed host behavior

- Identity transform, vertex (100,-50,200), H=100, screen center=(320,240): projected (370,215), SZ3=200, return 50.
- Depth 50000: the independently saturated IR3 is 32767 while depth remains 50000, return 12500.
- Negative depth maps to zero and reports divider overflow.
- `H=Z=65535, X=1023`: UNR projected X=1022; legacy division returns 1023.
- `H=Z=32767, X=1023`: UNR projected X=1022, also demonstrating quantization at a smaller depth.

The standalone and **complete local repository CMake build** passed 8 of 8 CTest suites with GCC on a fresh build tree. The checks were against deterministic host-side reference expectations, **not hardware-captured PS1 vectors**. No GitHub Actions result, Switch build or real-game render is claimed.

## Limitations

This is NOT a bit-for-bit hardware RTPS. The remaining gaps include GTE OFX/OFY fixed-point representation, MAC and FLAG overflow, interpolation IR0, FIFO semantics, per-stage rounding and exact fixed-point projection formula. The `project_unr_reference` screen stage still treats OFX/OFY as whole pixels rather than GTE register values.

The original PlayStation game data are not committed to GitHub. The original Wild Arms executable helper was previously audited at `0x800B70E8`; it reads projected GTE results and returns `SZ3 >> 2`.

Rebuild:

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```
