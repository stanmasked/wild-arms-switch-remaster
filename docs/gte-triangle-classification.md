# Conservative triangle facing from RTPT -> NCLIP

Introduced `include/gte_triangle_classification.hpp` and `tests/test_gte_triangle_classification.cpp`.

The experimental PlayStation GTE pipeline can now take three 3D vertices through `rtpt_nclip_reference()`, classify the NCLIP MAC0 sign, and return the full geometry result plus a **conservative** facing decision.

## Policy

A positive/negative signed oriented screen-space twice-area is not inherently front/back: polygon winding is determined by the game's geometry conventions. Callers must explicitly choose `FrontFace::PositiveArea` or `FrontFace::NegativeArea`. The output is `FrontFacing`, `BackFacing`, `Degenerate`, or `IndeterminateOverflow`. Only confidently back-facing triangles produce `safe_to_cull=true`. Degeneracy is returned separately, not silently discarded.

An overflowed NCLIP 32-bit MAC0 can have a sign inconsistent with the full arithmetic value. If MAC0 overflow flag bit15 or bit16 is present, the classifier returns `IndeterminateOverflow` and disallows culling based on the wrapped sign. This is an explicit **safety policy**, not a claim that original PS1 games behave identically in every overflow case.

## Verified tests

A reconstructed host project was configured and built using CMake and C++20, including the previous 28 suites and the new `wa_gte_triangle_classification_tests`. Full local CTest result: **29/29 passing**. The new test checks both winding conventions, zero area, positive/negative MAC0 overflow, full RTPT-to-NCLIP chaining and preservation of depth FIFO results.

## Limits / next work

The project's actual polygon winding convention has **not** been established from the original Wild Arms model or drawing-code paths. No real game asset classification was performed. Before adding backface culling to a renderer, inspect original polygon order and near-plane clipping behavior and compare against genuine PS1 GTE output captures. The GTE reference still does not establish complete hardware accuracy, no Switch-native runnable game exists, and CI has not been independently checked for this change.

The repository contains source, synthetic tests and documentation only, no original proprietary Wild Arms content.

Reproduce: `cmake -S . -B build && cmake --build build -j4 && ctest --test-dir build --output-on-failure`.
