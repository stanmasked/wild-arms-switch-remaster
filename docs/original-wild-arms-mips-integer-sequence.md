# Stage 186 — bounded linear integer instruction execution

`tools/mips_integer_sequence.py` executes a caller-supplied sequence of
supported MIPS integer instructions using `mips_integer_step.step`.
It preserves 32-bit GPR, HI and LO state across steps and returns
`completed`, `reason`, `index`, `executed` and final register state.
Execution halts on unsupported instructions, signed overflow, or a
configurable `max_steps` limit. Register zero is always zero.

Six synthetic tests passed locally in a Python 3 environment before
the code and tests were committed. The checked cases were signed
multiply + MFLO + arithmetic shift, unsupported memory instruction,
signed overflow, step limit, zero register, and empty input.

To re-run in the full repo:

```sh
python3 -m unittest discover -s tests -p test_mips_integer_sequence.py -v
ctest --test-dir build -R wa_mips_integer_sequence --output-on-failure
```

**Boundaries:** this is a linear integer sequence runner, not a MIPS
emulator. It does not model control transfers, delay slots, memory,
GTE, exceptions or hardware timing. It is not yet connected to
the original Wild Arms matrix code. The test was registered in CTest
and GitHub Actions; successful full-project CI is not yet established.
No copyrighted game executable bytes are stored or emitted.
