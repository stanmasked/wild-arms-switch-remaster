# RTPS: Separate IR3 saturation detection from SZ3 depth

Reference: https://psx-spx.consoledev.net/geometrytransformationenginegte/

PlayStation GTE RTPS special cases documented by psx-spx:
- MAC3 is the shifted post-sf 32-bit value in this standalone interface.
- IR3 is limited according to lm (signed or nonnegative range).
- For **sf=0**, the RTPS IR3 saturation **FLAG bit22** is tested using `MAC3 >> 12`, NOT the same value used to clamp stored IR3.
- For **sf=1**, the test uses MAC3 itself.
- SZ3 is a **separate** unsigned 16-bit depth result from MAC3 when sf=1, or MAC3 >> 12 when sf=0, with FLAG bit18 on saturation.

This standalone `rtps_depth_stage` function preserves the architectural distinction, with defined portable rounding of negative signed values. It models the expected subset of FLAG bits 22,18,31. It does not attempt to reproduce hardware FIFO updates, MAC3 overflow from the original matrix stage, DQA/DQB or full FLAG.

## Host-confirmed regression

An independent C++20 CMake target was compiled with GCC `-Wall -Wextra -Werror -pedantic`, and CTest passed **1/1**.

Representative checks:

| MAC3 | sf | lm | IR3 | SZ3 | flags |
|---|---|---|---:|---:|---|
| 50000 | 1 | 0 | 32767 | 50000 | bit22 |
| 50000 | 0 | 0 | 32767 | 12 | none |
| -1 | 0 | 1 | 0 | 0 | bits18,31 |
| 65536 | 1 | 0 | 32767 | 65535 | bits22,18,31 |

A first erroneous test used MAC3=100000000 at sf=0 expecting bit22, although MAC3 >> 12 is only 24414. The compiler rejected the expectation; replacing it with 140000000 (which shifts above 32767) fixed the test.

## Scope and follow-up

The new tests are registered as the **15th** CTest suite in the root CMake configuration. The test passed **in its isolated local project**. A new full-repository build, GitHub Actions run, original PlayStation comparison, and Nintendo Switch build **are not yet verified**.

Next integrate these rules into a new RTPS comparison route while keeping legacy references unchanged. No original game assets were committed.
