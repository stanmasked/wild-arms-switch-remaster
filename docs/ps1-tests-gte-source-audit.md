# ps1-tests GTE source audit: summaries are not RTPS output vectors

## Confirmed upstream source

GitHub source: https://github.com/JaCzekanski/ps1-tests

The actual upstream `gte/test-all/psx.log` file, fetched from the public GitHub repository, consists of the following lines:

```text
gte/test-all
Auto test all GTE valid opcodes/registers
Passed tests: 1150
Failed tests: 0
Done.
```

This report has **no per-case command opcodes, input register snapshots or expected output values**. It cannot be converted directly to the host comparator's JSONL fixture format. The 1150 successes are upstream's own test summary, **not 1150 imported or independently reproduced vectors in Wild Arms Remake**.

The upstream author's public [test generator](https://gist.github.com/JaCzekanski/4817d700b0abb908d3766ebd3b99b39c) shows that each test was originally modeled using 64 input registers, an instruction opcode and 64 expected outputs. Our comparator instead accepts a smaller set of 22 configured values and selected registers for RTPS. Conversion therefore requires **actual complete per-case data**, decoding the appropriate GTE register packing and instruction bits, and verification of the capture provenance. The short report alone is not enough.

## Implemented inspection

`tools/inspect_ps1_gte_log.py` provides a read-only inspection step:

```sh
python3 tools/inspect_ps1_gte_log.py /path/to/psx.log
```

Output is a JSON diagnosis: `summary_only`, `partial_register_log`, or `unrecognized`. None is silently reclassified as a valid external RTPS capture. Because these formats are not convertible with the available information, its CLI **exits 2** (non-success) rather than claiming a successful import. It does not write or mutate any game files.

`tests/test_ps1_gte_log_inspector.py` covers five cases: the real summary's literal content, nonzero failures, partial register-line dumps, unrecognized text, and mixed summary/register text. The test suite uses embedded metadata-level excerpts, **not hardware output vectors**.

## Verified locally

Configured and compiled the full CMake host project, then ran CTest. Result: **20/20 suites passed**; all five additional Python tests passed. This verifies format classification and existing portable code only, not GTE hardware accuracy. No PS1 hardware or independent emulator fixture has been imported, and native Nintendo Switch build / GitHub Actions success remain unverified.

## Next step

Locate original per-case input/opcode/output fixture arrays or run `gte-fuzz` on real hardware with capture support. Only then write and test a format converter that preserves the original 64 registers, decodes RTPS command settings (`sf`, `lm`), and maps compatible output registers. **Do not generate expected output from the host model and label it hardware.**
