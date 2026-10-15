# WILDARMS.EXE — bounded constant propagation for global pointer 0x800D2C3C

**Input:** user's own PS1 Wild Arms (USA) MODE2/Form1 image; no proprietary binary committed.

## Method
Scan each MIPS `LUI` in the EXE load image, propagating a known constant through a straight-line window of at most 16 following instructions. Account for register writes, `ADDIU`, `ORI`, simple arithmetic, and immediate memory accesses. Stop at branches and jumps to avoid speculative inter-block flows. Deduplicate matching memory-operation addresses.

## Actual image scan

| Criterion | Count |
|---|---:|
| Direct loads matched | 39 |
| Direct stores matched | 0 |
| Newly found matches beyond adjacent-pair scan | 0 |
| Largest observed LUI-to-memory distance | 1 instruction |
| Newly added synthetic unit tests | 7 passing |

## Interpretation
No new pointer initialization site was identified. **Zero detected stores is not evidence of no stores anywhere in the game.** This scanner does not trace across branches or function calls, model dynamic pointers, treat all MIPS opcodes exhaustively, analyze module code outside the EXE, or execute the game. Unknown instruction side effects can affect confidence; results are candidates pending disassembly review.

## Reproduction
```sh
python3 tools/inspect_disc.py 'Wild Arms (USA).bin' --json > inventory.json
python3 -m tools.scan_global_dataflow 'Wild Arms (USA).bin' inventory.json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Next investigation: locate initialization in boot code and overlay modules, and verify candidate address computations with control-flow-aware static analysis.
