# Strict gte-fuzz capture boundaries

Expanded `tools/import_gte_fuzz_rtps.py` after reviewing the upstream [gte-fuzz main.c](https://github.com/JaCzekanski/ps1-tests/blob/master/gte-fuzz/main.c), which prints 64 input registers, an opcode line and 64 output registers for each test.

The previous parser permitted an input-register line **after** the command marker, and tolerated arbitrary non-register text *inside* incomplete register blocks. Those can silently misassociate captured values with a different instruction. The importer now rejects:
- input register assignments after the instruction line;
- mismatches between RTPS's opcode 0x01 and command name;
- matrix/vector/translation selectors outside 0..3;
- unexpected nonempty text inside an incomplete register block.

Complete unrelated commands (such as NCLIP) may appear between RTPS captures without being falsely imported. Ordinary fuzz session headings remain legal between complete blocks. No artificial missing register data are filled.

Eight extra tests in `tests/test_gte_fuzz_strict_contract.py` exercise multi-capture streams, skipped unrelated commands, invalid opcode labels, impossible command selectors and corrupt or misplaced text. The existing seven converter tests remain enabled.

**Local verification:** fresh host CMake configuration and C++ build succeeded, and **22/22 CTest suites passed**. These are synthetic parser-contract tests, **not original console output**. No authenticated 64-in/64-out PlayStation hardware log is currently available, so PS1 GTE bit-accuracy remains unproven. GitHub Actions and a Switch game build were not verified.

To run: `cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure`.
