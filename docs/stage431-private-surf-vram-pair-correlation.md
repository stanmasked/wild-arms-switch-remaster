# Stage431 — compare two private paused Surf Village VRAM captures

## Background

Stages426–428 expose *candidate* original Wild Arms Surf Village 4bpp
palette rows and GPU/VRAM correlation instruments. Stage429 adds a local
PCSX-Redux raw 1 MiB VRAM fetch, while Stage430 constrains the source
by three observations of `running=false` around two byte-identical
raw reads.

Stage431 asks a narrower falsifiable question: **do particular CDSTG
candidate 16-word rows recur at the same 16-word aligned VRAM
coordinates in two separately captured, internally stable snapshots?**

This is **not** reconstruction or authentication of a real PS1 frame.
Even two byte-identical VRAM captures do not prove that the operator was
in Surf Village, that the CDSTG palette was actually selected by GP0,
or that the color data was resident at the moment the GPU drew a tile.

## Prerequisites — private files ONLY

- Original owner's Wild Arms (USA) `CDSTG.BIN` from a privately retained
  disc image. No original game data is uploaded to public GitHub.
- Two **distinct basename** captures from Stage430 in the same
  already-created private directory, for instance `surf_a` and
  `surf_b`; each basename denotes a complete 1,048,576-byte
  `.u16le.bin` plus `.capture.json` with the expected SHA-256.
- The operator scene labels must match, to reduce accidental cross-scene
  comparisons. Labels are **not authenticated scene proof**.

Recommended owner-local procedure:
1. Start PCSX-Redux using the owner's original game, reach Surf Village,
   and pause at a documented gameplay scene; confirm the PCSX-Redux web
   server is isolated from outside computers and the wider Internet.
2. Create `surf_a` using Stage430's double-read capture. Record
   emulator build, original disc revision, observed scene, and whether
   the GPU Logger replay was active in a separate private notebook.
3. Advance the original game to another documented moment, pause again,
   and create **separate** `surf_b` using Stage430. Do not overwrite A.
4. Compare the two snapshots and keep the output JSON private:

```sh
python tools/audit_surf_paused_vram_pair.py \
  /private/WildArms/CDSTG.BIN \
  /private/WildArms/stable-captures \
  surf_a surf_b \
  --map-index 2 > /private/WildArms/stage431-private-pair-report.json

python -m unittest discover -s tests \
  -p 'test_audit_surf_paused_vram_pair.py'
```

The example paths represent **owner-private storage outside the Git
checkout**. No network calls are made by this comparison tool. It does
not capture VRAM, start an emulator, export PNGs, sample screenshots,
or access any public game data store.

## Input verification

Before any palette matching, the tool:

- Requires two distinct safe ASCII basenames without traversal;
- Rejects symlinked manifest/snapshot paths, oversized/malformed JSON,
  duplicate manifest keys and mismatched manifest names;
- Requires the Stage430 double-read record (`snapshot_read_count=2`,
  `execution_flow_read_count=3`, three `running=false`
  observations and exact byte equality *reported by Stage430*);
- Checks each 1,048,576-byte source and SHA-256 of the **actual bytes
  read for comparison**, so corruption/truncation fails closed;
- Rejects a mismatched operator-provided scene label; compares
  two sources only when both manifests satisfy their narrow contract.

The manifest itself is neither signed nor emulator-authenticated.
A maliciously fabricated manifest and matching bytes can pass; this
tool verifies **internal consistency**, not external provenance.

## Candidate classification

The tool reuses the existing bounded genuine WA1-LZSS/CDSTG source
validator. It builds all candidate 16-word source rows from the
512-byte banks, retaining duplicated row membership across banks.

On each of two raw snapshots it tests only possible 4bpp CLUT grid
locations: `x_words in {0,16,...,1008}` and `y in {0,...,511}`.
This restricts scans to 32,768 nonoverlapping candidate memory cells.
The tool skips all-zero rows and rows with fewer than three distinct
nonzero colors by default; skipping simple palettes can cause false
negatives, and no-hit is **not** proof of original palette absence.

Each unique candidate row is classified:

- `COMMON_COORDINATES`: the exact 32-byte sequence appears at one
  or more identical grid locations in both snapshots;
- `BOTH_PRESENT_DIFFERENT_COORDINATES`: appears in both but with no
  shared coordinates;
- `FIRST_ONLY` / `SECOND_ONLY`: appears in only one capture;
- `ABSENT_BOTH`: no matching grid occurrence in either.

Counts of changed **16-bit words** and changed **16-word aligned
cells** provide coarse differences between whole VRAM snapshots.
For each candidate the report stores SHA-256 of row bytes, existing
bank/row indices, hit counts and at most 16 common coordinate samples
(configurable 1–64); full common-position counts remain exact when
sample output is truncated.

The output JSON is **PRIVATE EVIDENCE**. It never prints raw VRAM,
palette 16-bit words, decompressed sprites, pixel images or GP0 command
words. Hashes and coordinates may still reveal characteristics of a
copyrighted source and should not be uploaded to public CI.

## What this does NOT establish

- Actual PCSX-Redux loaded disc, field map, time/frame or camera state;
- Atomic snapshot of a specific GPU draw command;
- CLUT sample time or PS1 texture cache correctness;
- Bank/stream pairing, tile/sprite layout, palette transparency/STP;
- Original player-visible framebuffer match;
- Switch field rendering of a verified Surf Village location.

PCSX-Redux's GPU Logger may contain only commands since the most recent
VSync, not necessarily a complete game frame. To attribute a palette
to a particular roof or well, correlate **draw-time** GP0 logs and
texture transfers with a privately captured, independently verified
original framebuffer.

References:
https://pcsx-redux.consoledev.net/web_server/
https://pcsx-redux.consoledev.net/Debugging/gpu-logger/

## CI and acceptance

`tests/test_audit_surf_paused_vram_pair.py` contains **21 synthetic
regressions**: stable/moved/missing palette coordinates, duplicate
rows, VRAM boundaries, corrupt/malformed/untrusted manifests, unsafe
paths, unchanged/differing snapshots, sample caps and output privacy.
Original game data is never present in public CI.

Stage431 succeeds as an **instrument** only once all three GitHub
workflows pass at the exact PR commit. Evidence from an original
Surf Village session remains an independent, owner-private
follow-up—not a consequence of passing these synthetic tests.
