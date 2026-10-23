# Stage521 — strictly idempotent live GP1 controls in native first-frame import

The original private **Wild Arms (USA)** introduction GPU capture exposed a
previously unmodeled edge case. Its first complete VSync interval includes
live GP1 records in addition to GP0 graphics packets. The old Stage447
importer correctly refused all live GP1 but consequently could never import
this real capture even when those controls only repeated an already restored
GPU setting. None of the original bytes belong in this public repository.

The Stage521 importer records the exact pre-TraceBegin GP1 control words
for these four state-setting commands only:

- GP1(03) display enabled/disabled
- GP1(04) GPU DMA direction
- GP1(05) display VRAM origin
- GP1(08) display mode

A live first-frame GP1 word may be ignored by the **GP0-only** replay
adapter only if its **full 32-bit value exactly equals** the unique native
preamble restore word for that command. A duplicate preamble restore for
the same command is ambiguous and fails. An unobserved setting, differing
value, GP1 reset, command FIFO reset, IRQ acknowledgement, info read,
GPU readback, arbitrary metadata or unsupported typed record also fails
closed. A repeated control can occur more than once after TraceBegin.

The verifier retains the original native source bytes and their independent
SHA-256 checks. Ignoring a command proved equal to pretrace state does not
mean GPU side effects or more general register changes are modeled.
The new report counts accepted redundant words. Legacy reporting that
*all* unmodeled GP1 events were rejected becomes false when redundant
controls were admitted; the explicit narrower state-change rejection
flag remains true.

## Gate and limitations

All tests added for this stage use artificial ROM-free streams: positive
matching 03/04/05/08 restore controls, absence of a pretrace setting,
duplicate restore, real change, mixed matching/changing input and
side-effecting commands.

This adjustment is **not a complete GPU compatibility layer**.
Actual original captures may also contain unsupported GP0 opcodes,
frame-end subtleties or scene-specific geometry. It cannot by itself
prove an original screenshot or Surf Village, nor replace the genuine
GUI-produced V2 binary and independent screenshot. Maintain the
existing Stage516 strict five-input seal as pending until both the GUI
export and native first-frame importer agree on the same files.

Original GPU captures, source files, VRAM, game IDs, private hashes
and PNG remain in owner-private Google Drive, not public CI.

## Next native GP0 compatibility gate

A separately archived authentic INTRO capture also contains GP0(02), the
PS1 VRAM fill rectangle command. The current Stage437 strict packetizer
rejects this opcode and its GPU memory effects are not yet modeled by
that adapter. Do not silently drop or relabel GP0(02) to force the five-file
seal to pass. Implement and regression-test exact fill geometry, word
framing, bounds, mask/VRAM behavior and any affected drawing state as a
separate later stage. The Stage521 GP1 control proof solves only its
explicit state-equivalence subset.
