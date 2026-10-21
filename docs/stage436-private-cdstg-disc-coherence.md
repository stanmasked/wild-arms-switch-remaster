# Stage436 — source-to-extraction integrity AND Surf Village map coherence

## Problem this stage closes

Stage435 introduced a conservative local reader for the owner's original
single-track MODE2/2352 CUE/BIN. It can extract a private
`CDSTG.BIN` at ISO9660's recorded extent.

A correct file **size** and a successful write are not sufficient to
establish that the extracted game data corresponds to the original disc
and to the specific Surf Village map being restored. Files could be
damaged, stale, swapped between game revisions, or have wrong graphic
stream bounds. Stage436 explicitly checks that relationship using
**independent raw-source and extracted-file hashes** and the existing
Stage426 WA1 map/LZSS structural validator.

### Public implementation

`tools/audit_private_cdstg_disc_source.py` (PRIVATE local input only):

1. Parse owner-local `Wild Arms (USA).cue` and validate the referenced
   sibling `Wild Arms (USA).bin` as a single Mode2/2352 raw track.
2. Re-read ISO9660 PVD/root directory and find precisely one
   `CDSTG.BIN` extent with the established **76,021,760-byte** size.
3. Compute SHA-256 streaming over **every relevant original raw-sector
   user-data byte** of the ISO9660 extent (2048-byte Mode2/Form1
   payload, offset 24 of each 2352-byte source sector).
4. Independently hash the entire owner-private `CDSTG.BIN` extracted
   by Stage435. Reject the pair if any bit differs.
5. Run `audit_palette_candidates` from Stage426 against the locally
   extracted original resource. This validates the map-2 graphics
   pointer run and correctly bounded WA1-LZSS stream payloads.
6. Confirm the already observed expected 7 512-byte palette candidate
   banks and 7 bounded decoded streams, plus 16 rows per bank.
7. Recheck filesystem identities (inode, device, size, modification
   time) of both original BIN and extracted file after analysis, to
   catch concurrent mutation during these operations.
8. Emit **only metadata**, including original/extracted SHA-256,
   map/stream/bank counts and unverified historical claims. Neither
   original colors nor raw disc sectors are printed.

This is read-only and emits no new file unless the owner explicitly
redirects its terminal JSON to a private destination. The raw disc and
the extracted resource must **remain outside public GitHub**.

### Owner-local example

Prerequisites: locally stored complete original `.cue` and `.bin`
and a Stage435-extracted `CDSTG.BIN`. On the local computer:

```sh
# Existing owner-private original CUE/BIN and extracted CDSTG.BIN.
python tools/audit_private_cdstg_disc_source.py \
  '/private/WildArms/disc/Wild Arms (USA).cue' \
  /private/WildArms/extracted/CDSTG.BIN \
  --map-index 2 --expected-raw-sectors 270903 \
  > /private/WildArms/extracted/stage436-private-disc-proof.json

python -m unittest discover -s tests \
  -p 'test_audit_private_cdstg_disc_source.py'
```

The 270,903 raw-sector count comes **only** from Google Drive's
637,163,856-byte BIN size metadata (2352 bytes/sector). It is an
expected size guard, not independent authentication of its bytes or
the game's revision.

The Stage426 private source observations from earlier work are:
**7 candidate palette banks** and **7 next-pointer-bounded graphics
streams** on map #2. The equal counts are not evidence that bank
ordinal i is necessarily paired with stream ordinal i; that
assignment requires runtime PS1 GPU/VRAM upload proof.

### False claims explicitly prohibited

- Even a correct source-to-extract SHA-256 proves integrity of this
  *pair*, **not** that the disc SHA matches a reference retail pressing.
- A valid map-2 LZSS run and seven palette banks do **not** prove
  a chosen 16-color CLUT row, GPU texture page, bit-15/STP behavior
  or pixel-accurate Surf Village geometry.
- Nothing here starts PCSX-Redux or captures real Surf Village gameplay.
- The Stage435/436 privacy-sensitive paths, hashes, extracted source,
  disc images, decoded sprites, palettes and screenshots must never be
  committed or attached as public CI artifacts.
- Concurrent mutation checks are best-effort filesystem detection;
  without immutable or cryptographically signed capture media these
  are not an atomic proof against adversarial replacement.

### Synthetic CI

`tests/test_audit_private_cdstg_disc_source.py` contains 17 tests
built from an invented 24-sector Mode2/Form1 image from Stage435. Its
source/data hashes really do match the test ISO extent. For map
structure, it supplies a strictly synthetic mocked count contract;
Stage426's original bounded map parser has its own independent tests.
It checks wrong source bytes, wrong extracted bytes, stale sizes,
wrong disc sector count, bad CUE reference, structural mismatch,
filesystem mutation, source privacy and read-only behavior.

**The original 637 MB Wild Arms BIN is NOT downloaded by this stage.**
The connected Drive file cannot be fetched in one transfer because of
the 256 MiB download ceiling. The concrete next gate is an owner-local
run of Stage435/436, followed by a PCSX-Redux Stage432 screenshot/VRAM
witness for Surf Village and pixel-space ROI evidence from Stages433/434.
