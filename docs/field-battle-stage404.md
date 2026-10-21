# Stage 404 — isolated ARM reward persistence

This stage adds a versioned, two-slot journal for the **opt-in, asset-free ARM training prototype only**.

## Storage contract

- File base: \`sdmc:/switch/wild_arms_field/arm-rewards\`, with \`.a\` and \`.b\` slots.
- Format: 32-byte \`WAER\` v1 record, little-endian generation, EXP and Gella, reserved-zero fields and CRC32.
- Every write validates and syncs a temporary file before replacing only the older/invalid slot. A subsequent readback must match the exact published bytes.
- A cold boot restores the newest valid reward account. A single corrupt peer marks the journal degraded and is repairable from the valid slot; two corrupt slots fail closed and are never overwritten.
- The experimental ARM Victory B-close stores the updated reward account. Retreats and defeats do not write this journal.
- The ordinary field-save \`WAFS\` files and regular battle-progress \`WABJ\` files are separate and are never used as ARM reward storage.

## Verification

- Native C++ tests cover codec rejection, exact slot generations, reload, interruptions, CRC damage and fallback, refusal to overwrite two corrupt slots, and generation exhaustion.
- Intel Mac CTest and normal/experimental Switch NRO builds run in CI.
- The NeXium workflow uses two distinct emulator processes and the same isolated SDMC root. The second process must visibly load the first process's 8 EXP / 12 Gella balance; the journal bytes must remain identical across that read-only reboot.
- This is evidence from a Linux NeXium guest filesystem and host tests, **not** a physical Nintendo Switch power-loss or SD-card durability guarantee. Rewards remain prototype data, not reconstructed original PS1 progression.
