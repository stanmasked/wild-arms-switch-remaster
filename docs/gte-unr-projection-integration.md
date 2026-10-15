# Experimental UNR projection integration — 7 passing host suites

This change introduces a **separate comparison path**, `project_unr_reference()`, in `include/gte_projection_unr.hpp`. It retains the earlier `project_reference()` for differential tests and reuses `gte_unr_divide()` from `include/gte_unr_division.hpp`.

## Confirmed behavior

The UNR projection reports the quotient (Q16), divider overflow, packed screen XY, and host-only depth/coordinate clipping diagnostics.

A distinguishing test case:

| Inputs | Legacy approximate projection | New UNR reference |
|---|---|---|
| x=1023, y=0, H=65535, Z=65535, offsets=0 | screen x=1023 | screen x=1022 |

The new path uses the divider's Q16 result 0xFFFF, unlike conventional integer division yielding 0x10000.

Additional static assertions cover normal projection, divider overflow at zero depth, H=0, and far-depth clipping.

## Build verification

Locally assembled a complete CMake build containing seven targets consistent with the repository sources. Fresh CMake configuration, GCC compilation and `ctest --output-on-failure` passed: **7/7** (core, math, transform, projection, RTPS composition, UNR division, UNR projection).

GitHub repository files and CMake registration were read back after publication. **GitHub Actions CI has not been independently checked.**

## Known gaps — not hardware-accurate RTPS

- Screen offsets `ofx`/`ofy` are still modeled as whole pixels, not PS1 GTE fixed-point control registers.
- MAC accumulation widths/overflow, exact IR0, SZ FIFO, FLAG bits and perspective stage scaling are not reconstructed.
- The experimental `rtps_reference()` **still calls `project_reference()`**. The new UNR projection is deliberately separate until pipeline and flag semantics can be compared with hardware-level fixtures.
- No Nintendo Switch executable or gameplay renderer is produced by this work.

No original Wild Arms executable or assets were committed.

## Reproduce

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```
