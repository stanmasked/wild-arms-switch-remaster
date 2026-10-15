# Original Wild Arms: fixed-point sine and cosine lookup used in GTE matrix construction

## Correction to previous interpretation

The MIPS instructions near `0x800B7118` use the following address expression: a 12-bit angle is shifted left by two and added to the high-address base; `LW` then reads at an offset that resolves to **`0x800CBE44 + 4 * index`**.

This is a **direct, indexed table in the original PS-X EXE load image**, *not* a dereferenced global variable containing a pointer. Earlier descriptions of `0x800CBE44` as a pointer slot were incorrect and are superseded by this audit.

## Verified from the local original EXE

The table begins at virtual address `0x800CBE44`, contains **4096 entries**, and occupies **16384 bytes**. Each entry contains a signed 16-bit sine sample in its low halfword and a signed 16-bit cosine sample in its high halfword. Angles are indexed on a 4096-unit circle, and the numeric scale is approximately 4096 (Q12).

At cardinal indices `0,1024,2048,3072`, the pairs are respectively `(0,4096)`, `(4096,0)`, `(0,-4096)`, and `(-4096,0)`. All 4096 sine and cosine pairs were checked against mathematically computed samples of `4096*sin(2*pi*i/4096)` and `4096*cos(2*pi*i/4096)`; the greatest absolute distance from the nearest integer was **7**. This shows trigonometric meaning, but not the bit-exact procedure by which the original lookup data was produced.

Six direct indexed loads were verified in the rotation matrix constructor at:

`0x800B7140`, `0x800B7168`, `0x800B71A4`, `0x800B71CC`, `0x800B7230`, `0x800B7264`.

All six use `LUI`, `ADDU`, and `LW` to address the same table base. The builder reads 16-bit input angles from offsets `a0+0`, `a0+2`, `a0+4`, masks angle indices with `0x0FFF`, scales by four and uses lookup values while generating the nine halfword rotation matrix slots. The current static audit does not establish every branch-dependent sign and coefficient calculation.

## Verification and asset boundary

```sh
python3 tools/audit_gp0_trig_table.py /private/path/WILDARMS.EXE
cmake -S . -B build
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

The **private original executable was examined locally only**. The new tool reports aggregate comparisons and instruction addresses; it neither prints nor commits the original 16 KiB table. Tests use their own independently generated, tiny synthetic lookup fixture, not original game assets.

Ten new regression tests pass; the complete locally compiled project passed **49/49 CTest suites**. Original table reconstruction at runtime, exact rounding, hardware-exact GTE simulation, Nintendo Switch native rendering, and playable game status are not implied by this result.

## Next investigation

Decode branch-dependent selection of sine/cosine halfwords, table-index sign handling, and signed multiplication with coefficient shifts in `0x800B7118`. The host port should ultimately reproduce the game's lookup semantics without silently replacing the original Q12 table with platform floating-point trigonometry.
