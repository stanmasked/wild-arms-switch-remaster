# Stage526 — actual GUI-produced V2 and Stage516 private five-file seal VERIFIED (Sony intro)

The pinned public-code-only PCSX-Redux build
[Actions #40042606963](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/40042606963)
**completed successfully**, including upstream host tests, guest PS1
programs, OpenBIOS, AppImage packaging and packaged binary smoke tests.
No original game bytes were part of this public CI run.

## Authentic Player source (owner-private only)

An owner-local Xvfb session loaded an original Wild Arms (USA) native
`PSXGPUDUMPv1r1` into the compiled and pinned PCSX-Redux GPU Dump Player,
then stepped the actual detached GPU to **Frame 1**. The original
independently captured Player GUI image remained byte-pixel-compatible
with the detached Frame-1 VRAM on its 41,850-pixel unscaled RGB ROI.

Click automation targeting the native Player toolbar did not activate
any of the lower-row controls, although opening a file dialog and a main
menu worked. This was **not** a failure of the V2 writer. The actual
ImGui GUI can also be navigated by keyboard: in this exact tested UI
configuration, Tab selected the
`Export Step 1 private VRAM...` button and Enter activated **that
native GUI button**. With the opt-in `WA1_PRIVATE_STEP1_V2_PATH`
pointing to an existing owner-private directory, the patched C++
writer produced a new **1,048,640-byte V2** file by exclusive create.
No Python script constructed or forged that V2.

Separate private checks verified its format, Frame==1, exact 1MiB
raw VRAM, CRC32, native source GPU dump SHA-256 binding and exact
equivalence to the original independently extracted Player Frame 1.

## Full Stage516 binding and independent Drive readback

Using the precise public `tools/` source extracted from the
[public-code verifier bundle](https://github.com/stanmasked/wild-arms-switch-remaster/actions/runs/40047372614),
the owner-private procedure imported the authentic first-frame ordered
GP0 JSONL and ran
`tools/seal_private_player_frame1_archive.py seal`
on five **distinct, non-hardlinked regular** original-game evidence
inputs:

1. original native GPU dump;
2. native initial/pretrace VRAM;
3. imported first-frame ordered GP0 JSONL;
4. actual GUI-produced, dump-hash-bound V2;
5. unscaled PNG cropped only from the separately captured genuine GUI
   screenshot, not rendered from the V2 bytes.

The strict exact-RGB ROI and **require-changed-ROI** gates passed.
The resulting Stage516 manifest contains only owner-private SHA-256,
file sizes, ROI coordinates and strictness settings.

All five files and the manifest were ZIP-archived, uploaded to
**owner-only private Google Drive**, then **downloaded again** and
checked for exact ZIP digest equality and CRC. In a fresh private
directory, official `seal_private_player_frame1_archive.py verify`
returned

`PRIVATE_FRAME1_ARCHIVE_INTEGRITY_AND_RGB_VERIFIED`

with no edits or provenance substitutions.

## Interpretation — tightly bounded

- **PASS:** native import, actual GUI Step-1 V2, detached Frame 1,
  strict five-input SHA/CRC/RGB seal, independent Drive re-read.
- **NOT a cryptographic attestation:** the screen capture was observed
  independently and preserved with X11/GUI evidence, but the public
  file-integrity seal cannot cryptographically prove an operator-supplied
  screenshot's on-screen origin or emulator executable provenance.
- **NOT Surf Village:** this is the **Sony publisher introductory scene**.
  The developer-logo scene still contains unsupported GP0(2C)/(64),
  and actual Surf Village gameplay graphics have not been captured and
  verified.
- **No private game data in public GitHub:** the actual GPU dump, original
  VRAM, GP0 words, V2, screenshot pixels, ZIP archives, game identifiers
  and original-content SHA-256 remain only in owner-private Drive.

The local keyboard GUI capture and sealed archive are reproducible from
the owner-private retained tools and captured inputs, without
publishing licensed content or reducing the seal's fail-closed checks.
