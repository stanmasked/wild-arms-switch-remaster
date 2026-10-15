# MAC44 + special IR3/SZ3 RTPS integration

The previously prepared local patch was published to the private repository.

## Files
- `include/gte_rtps_mac44_depth_reference.hpp`: new, separate RTPS reference implementation combining signed 44-bit stepwise MAC accumulation, IR stage, RTPS-specific IR3/SZ3 rules, UNR perspective divide, and OFX/OFY screen stage.
- `tests/test_gte_rtps_mac44_depth_reference.cpp`: tests ordinary projection, depth=50000, sf=0 special case and negative/zero depth.
- `CMakeLists.txt`: registers the sixteenth CTest suite.

## Verified locally

After restoring the missing `src/core.cpp` source in the locally staged full project, ran a new CMake configure, GCC build and CTest. Result: **16/16 tests passed**. Source, tests and CMake were separately fetched back from the private GitHub repository following publication.

Example important distinctions:
- `sf=1`, translation Z=50000: `IR3=32767` (saturated), `SZ3=50000`, flag22 set.
- `sf=0`, translation Z=12 and zero Z vertex: post-sf `MAC3=49152`; `IR3=32767`, `SZ3=12`, flag22 clear.
- Negative depth: `SZ3=0` and overflow flags are set in the modeled path.

## Limitations

The C++ model is **not independently validated against PS1 hardware RTPS vectors**. Exact hardware MAC44 flags, saturation, IR0, depth FIFO and pipeline timing require additional work. Tests with expectations derived from our own model do not establish console equivalence. GitHub Actions workflow runs and status checks were queried for commit `71e74d1c68b938ec6cdcff99d45e4e9a41242cbd`, but those APIs returned empty arrays, so **CI success is not verified**. No Switch native binary or playable game has been built.

No copyrighted Wild Arms game data was committed.
