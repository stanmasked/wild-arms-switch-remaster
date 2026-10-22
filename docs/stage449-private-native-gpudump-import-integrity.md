# Stage449 — verify native GPU dump, initial VRAM and imported trace belong together

## Why the owner needs a second roundtrip check

Stage447 imports the **first VSync-delimited GP0 interval** from the
official PCSX-Redux `PSXGPUDUMPv1r1` file into two separate private
files: (a) the original one-megabyte VRAM snapshot contained in the
native preamble, and (b) Stage437's complete packetized JSONL
representation of the supported first-frame GPU GP0 words.

While these files share a capture session *when first created*, their
names and locations can be moved accidentally. A correct-looking
JSONL paired with VRAM from a different day, different game, or
different GPU capture is **not valid evidence** of draw-time
texture or CLUT provenance.

Stage449 independently reconstructs the entire first-frame GP0
wordstream from the native dump, validates the stored Stage437
JSONL and compares **every packet, every 32-bit word, and every
byte of the original VRAM** against the extracted files.
It never assumes that a matching filename or frame number proves
shared provenance.

## Owner-private verifier

`tools/verify_private_pcsx_native_gpudump_import.py`:

1. Fails closed on missing, symlinked, aliased, oversized or
   incomplete owner-private files; strictly validates optional
   expected SHA-256 and frame arguments.
2. Re-parses the original native typed GPU dump using the Stage447
   strict native reader. Rejects unsupported live GP1/readbacks or
   GPU commands, truncated frames and invalid bootstrap.
3. Reconstructs the exact original one-megabyte VRAM bytes,
   rejects **any differing byte** in the imported VRAM file.
4. Reads the existing Stage437 JSONL through its strict parser,
   checks the initial VRAM hash, frame label (when requested),
   and compares **all GP0 packet words and packet boundaries**
   against a newly packetized version of the same native dump.
5. Optionally checks the exact native GameID against an
   **independently operator-provided expected serial**, and
   optionally verifies the native dump SHA-256 against an
   independently recorded digest. Missing/mismatched GameID or
   invalid padding/duplicated GameID are rejected. A GameID
   supplied by an operator **does not authenticate the disc**,
   and the ID string is not printed in the resulting report.
6. Outputs a bounded metadata-only report containing verified
   word count, packet count, SHA-256 digests, optional check
   indicators and explicit proof-boundary flags. Raw GPU words,
   palette values, original VRAM and the GameID text are **not
   copied into JSON**. Even SHA-256 hashes may expose information
   about private data and should **never be made public**.

## Owner-local example (after a genuine GPU capture)

```sh
# The GPU dump is created on the owner's own computer by
# PCSX-Redux Debug > GPU > Show GPU dump recorder / player.
python tools/import_private_pcsx_native_gpudump.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/before-first-frame.u16le.bin \
  /private/WildArms/gpu/first-frame.jsonl \
  --frame 0 \
  > /private/WildArms/gpu/stage447-import-private.json

# Check the imported artifacts again against the original GPU dump:
python tools/verify_private_pcsx_native_gpudump_import.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/before-first-frame.u16le.bin \
  /private/WildArms/gpu/first-frame.jsonl \
  --expected-frame 0 \
  > /private/WildArms/gpu/stage449-integrity-private.json

# Optional: append --expected-native-game-id only after the
# operator has INDEPENDENTLY established the exact disc serial.
# Optional: --expected-native-sha256 from independent safe record.
```

These paths are examples; no real Wild Arms GPU dump has been
captured in this project session. The original user's full
PlayStation BIN/CUE resides on their private connected Drive
and has **not** been uploaded to public GitHub CI. The independent
GameID check requires a trusted separate source, not a guess.

## What exact equality does *not* establish

- The dump's true emulator executable revision or absence of
  instrumentation/recording bugs; the upstream source merely
  documents the native format.
- Whether the original Wild Arms game was at Surf Village,
  the camera position, a specific roof/well being visible, or
  an authenticated match to a paused screenshot witness.
- The actual hardware GPU's texture/CLUT caches, drawn polygons,
  bit15/STP behavior or final framebuffer color.
- Whether the original-game disc extraction was sourced from
  the same revision. That requires a separately checked disc
  identity and original visual reference.

The verifier establishes **file-to-file consistency**, which is
a necessary prerequisite for using Stages437–445's conditional
source→A0→GP0(80)→UV→CLUT lineage. It is not a claim that the
original image has been reconstructed.

## Synthetic-only CI

`tests/test_verify_private_pcsx_native_gpudump_import.py` contains
**17 ROM-free tests** covering exact imported VRAM/JSONL equality,
changed one-byte VRAM, changed/missing/swapped GP0 packets,
operator expected GameID and native hash mismatches, no GameID,
duplicated/trailing/malformed native IDs, corrupted JSONL,
symlinks, frame mismatches and privacy.

The project does not embed the original disc, original GPU dump,
decoded CDSTG, screenshots, VRAM or report metadata in the public
repository.
