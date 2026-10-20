# Wild Arms Remake — Stage369: both A/B battle journals damaged

This research test is stacked on PR #58 and depends on its real
NeXium proof of four earned victories, 32 prototype EXP and 48
prototype Gella on the same isolated SDMC root. No source game ROM,
disc assets, BIOS, or firmware are part of the CI.

The test preserves both valid WABJ gen5 A and gen6 B as immutable
evidence, then modifies **only byte 48** of the outer CRC32 in *each*
committed copy. Both files remain on disk with their exact pre-fault
payloads; every CRC parser must reject both. In this state the reader
cannot safely choose any historical progress. Returning Corrupt
instead of guessing is intentional. Without an explicit restoration
of independently backed-up evidence, stored progress is unavailable.

Two additional genuinely independent NeXium processes, 23 and 24,
reusing that very same SDMC, check that:

- The initial ZL panel shows 0 wins, 0 EXP and 0 Gella, instead of
  unverifiable four historical victories or a fabricated payout.
- The player can open an R training battle and retreat using B.
  The retreat is reflected *only* in the current volatile session
  history; the file writer must fail closed without replacing either
  invalid committed record or creating a field-save record.
- The subsequent fresh process restarts from 0 instead of persisting
  the failed-to-write retreat, and again safely refuses overwrite.
- Both damaged A and B remain **byte-for-byte** unchanged after both
  sessions, enabling later manual recovery from the preserved pristine
  source copies. Neither script nor game silently resets or deletes
  historical journal files.
- Six real observed Xvfb frames, independent guest process PIDs,
  controlled no-A attack key sequences, and genuine SDMC copies
  undergo read-only image/CRC verification.

The companion 18 synthetic adversarial tests are not evidence of
actual emulator gameplay. Failure to load *both* copies cannot
promise recovery of the four earned victories; that would require
external backup or a user-authorized data recovery workflow. The
test-only prototype does not assert physical Switch FAT durability.
