# External PlayStation GTE RTPS differential verification

The host project now exposes full-output comparisons for separately captured GTE results, instead of claiming correctness based only on test cases calculated by our own model.

**External validation status: pending capture/import. No actual hardware result vectors have been ingested yet.** Passing the fixture-contract test does not certify PS1 hardware fidelity.

## Verified references for future captures

- [JaCzekanski ps1-tests](https://github.com/JaCzekanski/ps1-tests): PS1 test collection including `gte-fuzz` and `test-all`, suitable for capturing registers on physical hardware.
- [psx-spx Geometry Transformation Engine](https://psx-spx.consoledev.net/geometrytransformationenginegte/): documented GTE commands and flag behavior.
- [psx-spx GTE Pipeline Timings](https://psx-spx.consoledev.net/gtepipelinetimings/): independently measured hardware timing (not currently implemented by our host reference).

## Workflow

Build the host runner:

```sh
cmake -S . -B build
cmake --build build -j4
python3 tools/compare_gte_rtps_vectors.py build/wa_gte_reference_runner captured-gte-rtps.jsonl
```

The JSONL input consists of one object per captured test, with the following fields:
- `source`: `hardware` or `external_emulator` (a declared provenance label, **not independently authenticated**).
- `name`: optional description.
- `input`: exactly **22 integers**, in order: 9 rotation coefficients, 3 translation values, 3 vertex values, projection H, OFX, OFY (signed 16.16), DQA, DQB, sf and lm.
- `expected`: a nonempty dictionary mapping any of `sxy2, sz3, ir0, ir1, ir2, ir3, mac0, mac1, mac2, mac3, flag` to captured integer output.

The tool compares only registers present in `expected`, prints individual discrepancies and exits with failure on any mismatch. The tool **refuses empty test files**, missing expected values, and the provenance label `host_reference`. Capturers must independently authenticate that the data genuinely came from external hardware or emulator, not relabel locally generated outputs.

Input values must respect each PlayStation register's bit width; the host runner currently uses C++ integer conversions and does not validate out-of-range values. Use only well-formed captures. Hardware run scripts and genuine captured fixtures still need to be provided.

## Confirmed local checks

A fresh local CMake configure/build and full CTest run passed **19/19 suites**. Five independent Python unit tests of the *comparison infrastructure* passed. The C++ runner was compiled with GCC C++20 and executed on a normal synthetic example.

No hardware-derived RTPS fixture was supplied or passed; all prior reference implementations are still experimental. The actual game engine, Nintendo Switch build, and GitHub Actions statuses are separate incomplete tasks. No original Wild Arms game assets are checked into the repository.
