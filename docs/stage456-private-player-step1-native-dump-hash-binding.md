# Stage456 — bind detached Player Frame 1 export to the loaded native GPU dump

## Purpose

Stage455 added a Frame-1 detached software GPU VRAM export, but the exported
container did not identify which native GPUDUMP had been loaded. Stage456
extends the owner-local patch to hash the exact byte stream read by
`GPUDumpReader`, then freezes that digest alongside the Player's frame label
and 1 MiB VRAM snapshot.

This does **not** make the patched emulator binary itself attested, nor does
it independently authenticate a separately supplied PNG. It does make the
snapshot's declared native-dump identity verifiable against the exact private
native dump being audited.

## Patch generator

`tools/patch_private_pcsx_gpudump_player_step1_dump_hash.py` generates one
four-file patch against a **clean, pristine** PCSX-Redux checkout pinned to
`de4a33e9a69abec4f567ae33567537f867dc2bba`. It includes the Stage455 GUI
export patch in memory and then extends the core reader and Player GUI.

Do not first apply the Stage455 patch separately: Stage456 generates the
combined diff from pristine upstream source anchors.

```sh
python tools/patch_private_pcsx_gpudump_player_step1_dump_hash.py \
  /private/tools/pcsx-redux

python tools/patch_private_pcsx_gpudump_player_step1_dump_hash.py \
  /private/tools/pcsx-redux --apply
```

The first invocation validates the patch with `git apply --check` without
modifying the checkout. The second explicitly modifies the owner's local
checkout. It refuses an unexpected upstream commit or dirty working tree.
After applying, build PCSX-Redux locally according to upstream instructions.
The generated patch is not claimed to have been built against the complete
emulator by this repository's CI.

## New binding path

1. `GPUDumpReader::open(IO<File>)` requires a word-aligned dump and reads
   the complete file into the reader's word buffer. It hashes those exact raw
   bytes before interpreting/swapping packet words; partial reads fail closed.
2. The digest is stored on that reader and exposed read-only through the
   loaded `GPUDumpPlayer`.
3. The export button remains enabled only while paused at `Frame 1`.
4. At button-click time, the GUI freezes the actual Player frame counter,
   the Player's detached GPU VRAM and that loaded reader's SHA-256.
5. The Save dialog writes the already-frozen state; stepping or changing
   another emulator instance while choosing a filename cannot change it.
6. The strict verifier compares the embedded digest with SHA-256 of the
   owner-supplied native GPUDUMP before accepting any RGB comparison.

The SHA-256 helper is self-contained and has compiled known-vector regression
tests for the empty string, `abc`, and one million `a` bytes. It processes
the input in 64-byte blocks without allocating a padded duplicate of the
whole dump. The complete upstream GUI patch still requires a local build.

## Binary container v2

The export is exactly `64 + 1,048,576` bytes:

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 16 | Magic `WA1STEPVRAMv2` plus three NULs |
| 16 | 8 | Little-endian captured Player frame; must be 1 |
| 24 | 4 | Little-endian VRAM byte length; must be 1,048,576 |
| 28 | 4 | CRC32 of raw VRAM bytes |
| 32 | 32 | SHA-256 of exact native GPU dump bytes read by the Player |
| 64 | 1,048,576 | Detached Player VRAM as u16 little-endian words |

Version 1 containers are deliberately rejected by the v2 verifier rather
than interpreted without a dump identity. CRC32 remains accidental-corruption
detection, not authentication. The cryptographic source binding is the
embedded SHA-256 comparison.

## Owner-private verification

After the patched emulator is built, open the target original native GPUDUMP,
rewind, press Step once, ensure the Player says Frame 1, export the VRAM file,
and capture an unscaled lossless PNG ROI from that Player preview.

```sh
python tools/verify_private_gpudump_player_step1_dump_hash.py \
  /private/WildArms/gpu/surf.gpudump \
  /private/WildArms/gpu/first.before.u16le.bin \
  /private/WildArms/gpu/first.gp0.jsonl \
  /private/WildArms/gpu/player-step1.v2.bin \
  /private/WildArms/gpu/player-step1-roi.png \
  --x 100 --y 60 --width 32 --height 24 \
  > /private/WildArms/gpu/stage456-bound-step1.private.json
```

These are illustrative paths and coordinates, not files present in this
development session. The verifier checks Stage451 native/pretrace integrity,
the snapshot's native-dump SHA-256, the v2 header, frame number, CRC32,
optional independent SHA-256 expectations, and exact RGB555-derived ROI
equality. It reports only hashes, counts, and status, not raw pixels.

## Remaining limitations

- The patch must be built and run locally; this project CI does not build
  PCSX-Redux or attest the resulting binary.
- A malicious or modified emulator could fabricate its own embedded digest.
  Treat the patch source and local build provenance as part of the evidence.
- The PNG is still operator-supplied. A stronger capture would export the
  Player's RGB preview from the same UI action or record it through a trusted
  owner-local capture route.
- The original Wild Arms dump, BIN/CUE, CDSTG, VRAM, screenshots, raw graphics,
  and private reports/hashes must remain outside public GitHub and CI.
- No original Surf Village scene reconstruction is claimed by synthetic tests.

## Validation

`tests/test_verify_private_gpudump_player_step1_dump_hash.py` adds 22
ROM-free tests for the v2 format, wrong source digest, CRC, length/frame,
RGB equality, privacy and patch generation. It also compiles the exact
self-contained C++ SHA-256 helper when a host C++ compiler is available and
checks three standard known vectors against Python's `hashlib`.
