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
The Disc analysis unit tests workflow fetches this exact upstream commit and runs the generator's `git apply --check` against the real four source files. The separate `PCSX-Redux patched build` workflow fetches the pinned source and submodules, applies this combined patch in a disposable CI checkout, and builds the full emulator plus host tests/tools using the upstream Linux build container. These checks establish patch applicability and CI compilation only; they do not attest the owner's local binary or replace the private runtime capture.

## New binding path

1. `GPUDumpReader::open(IO<File>)` requires a word-aligned dump and a
   successful seek to byte zero, then reads the complete file into the reader's
   word buffer. It hashes those exact raw bytes before interpreting/swapping
   packet words; partial or invalid-sized reads fail closed. Exceptions raised
   by the pinned `File::size()`, `rSeek()`, or `read()` implementations are
   converted to a failed open, with the previous digest and packet buffer cleared.
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
whole dump. The dedicated CI build checks compilation against the pinned
upstream source; the owner's local build and runtime capture remain necessary
to validate the private Wild Arms GPU dump.

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

- The patched emulator must still be built and run in the owner's private
  environment against the original GPU dump. CI compiles a disposable patched
  checkout but does not attest the owner's binary or certify runtime behavior.
- A malicious or modified emulator could fabricate its own embedded digest.
  Treat the patch source and local build provenance as part of the evidence.
- The PNG is still operator-supplied. A stronger capture would export the
  Player's RGB preview from the same UI action or record it through a trusted
  owner-local capture route.
- The original Wild Arms dump, BIN/CUE, CDSTG, VRAM, screenshots, raw graphics,
  and private reports/hashes must remain outside public GitHub and CI.
- No original Surf Village scene reconstruction is claimed by synthetic tests.

## Validation

`tests/test_verify_private_gpudump_player_step1_dump_hash.py` adds 25
ROM-free tests for the v2 format, wrong source digest, CRC, length/frame,
RGB equality, privacy, patch generation, and fail-closed native I/O. It also compiles the exact
self-contained C++ SHA-256 helper when a host C++ compiler is available and
checks three standard known vectors against Python's `hashlib`.

## Stage476 follow-up — thrown seek failure must stop before parsing

The pinned upstream `src/support/file.h` declares the base `File::rSeek()`
as throwing by default, and `src/support/file.cc` shows that
`PosixFile::rSeek()` throws `std::runtime_error` when `fseek()` fails.
The patch's reader catches that exception and rejects the open; it also
rejects backends that return a negative seek result.

The compiled C++ regression harness counts file-read calls and calls to the
vector-backed `GPUDumpReader::open()` header-validation overload. For both
the thrown-exception and negative-return seek failures, it asserts that no
read or header validation starts, the digest is zeroed, and the reader buffer
remains empty. A source-order regression also checks that rewind/read
exceptions are handled before digest calculation and header validation.

This remains a synthetic host regression against a mock File backend; the
pinned upstream source establishes the real exception semantics, while the
separate patched-emulator build and private runtime capture retain their
own validation gates.

## Stage477 follow-up — Player load must stop before GPU setup

The synthetic C++ harness now also mirrors the relevant ordering in the pinned
`GPUDumpPlayer::load()`: unload the prior player state, open the reader, and
only then create and initialize the detached GPU and rewind through packets.
A valid mock dump must reach `GPUDumpReader::next()`; after that, a thrown
rewind failure or a negative-return failure must make `load()` return false
without file reads, GPU setup, or packet iteration, and the reader's digest
must be zero. The same negative-return case is checked through the Player
path, not just the reader overload.

This remains a synthetic mock-backed regression, not evidence of a private
Wild Arms dump being loaded by a locally built emulator. The latest
Stage477/478 Disc analysis and patched-build Actions runs are queued; no new
pass is claimed until they finish.

## Stage480 follow-up — avoid hashing a native dump twice

The file-backed reader validates the seek and completes the exact-size read,
then transfers the untouched byte buffer to the vector overload. That overload
computes SHA-256 once, before endian conversion, and publishes the digest only
after the native GPUDUMP header validates. This preserves the fail-closed
identity semantics while avoiding a second full pass over large dump files.

The regression tests assert that the file path delegates only after a complete
read, that the raw digest is computed before byte swapping, and that the digest
is committed only after header validation. CI is still pending; this change is
not marked validated until the current-head workflows complete.
