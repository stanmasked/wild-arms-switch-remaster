# External GTE vector validator: register-range hardening

This follow-up hardens `tools/compare_gte_rtps_vectors.py` and expands `tests/test_external_gte_fixture.py`.

## Input schema

Exactly 22 integers, in the documented order. Each position now has an enforced range:
- Rotation matrix (indices 0–8), vertex (12–14), and DQA (18): signed 16-bit.
- Translation (9–11), OFX/OFY (16–17), and DQB (19): signed 32-bit.
- Projection H (15): unsigned 16-bit.
- sf and lm (20–21): exactly 0 or 1.

Expected output register values are range-checked: SXY2/FLAG unsigned 32-bit; SZ3 unsigned 16-bit; IR0 0..4096; IR1–IR3 signed 16-bit; MAC0–MAC3 signed 32-bit. Python boolean values are rejected as integers. Missing fields and unsupported names are rejected. Comparison-runner invocation has a 10-second timeout.

The provenance `source: hardware|external_emulator` is **a user-provided claim**, not proof of provenance. No authenticated hardware recordings have been added to the repository.

## Confirmed local results

- 13/13 Python validator tests passed (up from the original 5).
- GCC/CMake and full CTest run passed: **19/19 suites**.
- Verified end-to-end comparator invocation via compiled `wa_gte_reference_runner` using an explicitly **synthetic, model-generated control**, not an external emulator capture. With unchanged values the comparison returned no differences; deliberately changing the expected SZ3 from 200 to 201 produced `{'sz3': {'expected': 201, 'actual': 200}}`.
- This control **must not** be treated as independent evidence of PlayStation GTE accuracy, regardless of the claimed source label in a temporary fixture.

## External research

[JaCzekanski ps1-tests](https://github.com/JaCzekanski/ps1-tests) lists `gte-fuzz` and `test-all` for real console hardware testing. Those are useful capture candidates, but their existence does not establish that any GTE output is available in our required 22-input/11-output JSONL format. A capture adapter and provenance verification remain necessary.

## Known gaps

The C++ runner currently assumes its direct stdin input was prevalidated by the Python tool; direct invocation can narrow out-of-range values. Future work: enforce register-width bounds at the C++ runner boundary too, and develop a converter for genuine external captures. No Switch native binary or bit-exact GTE certification is claimed.
