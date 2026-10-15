# Wild Arms GTE MVMVA control audit

The original PlayStation EXE was inspected locally; game binary data was not uploaded.

At address `0x800B68FC`, the instruction word is `0x4A486012`. It decodes as GTE `MVMVA` with `mx=0` (rotation matrix), `v=0` (V0 input), `cv=3` (no translation addition), `sf=1` (12-bit shift) and `lm=0` (signed intermediate limiting).

The helper at `0x800B68E8` loads V0, issues MVMVA and writes IR1, IR2, IR3 to output word offsets +0, +4, +8. This identifies the transformation selection, not its runtime matrix coefficients or guaranteed hardware-bit-exact results.

Reproduce using a locally extracted EXE:

```sh
python3 tools/audit_gp0_mvmva_control.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The local EXE audit returned `matched_original_command: true`. Twelve synthetic tests pass, and full local host CMake/C++20 build verification passes **46/46 CTest suites**. This does not establish a playable native Switch game, hardware-exact GTE, or original GP0 texture values.

Next trace where the active rotation matrix is loaded and evaluate MVMVA in the existing host reference model.
