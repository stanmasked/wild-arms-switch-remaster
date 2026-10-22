# Stage438 — reconcile ordered GPU transfers with a separate post-packet VRAM snapshot

## Why another verification is necessary

Stage437 conditionally replays supported GP0(A0) CPU-to-VRAM and
GP0(80) non-overlapping VRAM copies over an original *pre-packet*
1,048,576-byte raw VRAM buffer. It records the 16-word CLUT contents
predicted **before** supported 4bpp textured draws. It does not rasterize
GPU drawing, emulate the CLUT cache, or authenticate trace completeness.

A separate raw VRAM snapshot *after* the complete packet stream gives us
a falsifiable independent observation: when the predicted final memory
was not overwritten by an unmodeled GPU draw, does it equal the snapshot?
This stage adds **Stage438 post-packet reconciliation** to the Stage437
private timeline tool. It never publishes original pixel or palette data.

## Conservative comparison scopes

The only supported cases are:

1. **Zero GP0 drawing packets in the submitted trace.** Every modeled
   VRAM word is deterministically comparable. The tool compares all
   524,288 u16 words (1,048,576 bytes) to the independent post snapshot.
   Any mismatch invalidates exact replay for this trace. It is still
   conditional on capturing a complete and correctly ordered stream.
2. **One or more GP0 drawing packets.** Because GPU polygon and
   rectangle rasterization is NOT implemented, all VRAM contents are
   conservatively treated as unknown after the last draw. Only words
   explicitly refreshed by a supported A0 upload or proven-source 80h
   blit **after that last draw** qualify as final comparable words.
   If they mismatch the actual post snapshot, replay is falsified.
   Pixels that may have been written by drawing are never scored as
   correctly predicted.
3. **No comparable words after a draw.** The verdict is `null`, not
   success. With `--require-post-match`, no-evidence and mismatch
   both terminate with an error.

Output reports all-pixel versus known-only scope, observed post-VRAM
SHA256, number of known and unknown u16 words, mismatched known words,
and whether all actually comparable words agree. No decoded RGB,
palette words, GPU transfer packet data, or raw source memory enters
the report. **The report and hashes themselves remain private.**

A known-words match does NOT mean complete GPU replay is correct. It
only checks the explicitly transferred memory under the preceding
simulation assumptions.

## Owner-private example

This experiment needs THREE synchronized private assets:
- Original `CDSTG.BIN`, extracted from the user's own complete disc.
- Full raw PS1 VRAM sampled **before the first packet** of an original
  ordered, complete and correctly packetized GP0 trace.
- Full raw PS1 VRAM sampled **after the final packet** of that trace,
  without unrelated CPU/GPU operations in between.

A Stage432 paused gameplay screenshot and post-pause VRAM are **not
automatically a matching pre- or post-packet frame capture**. The
required independent GPU instrumentation is not provided by the
PCSX-Redux REST screen capture API. Do not mislabel such files to
make the check pass.

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/before.u16le.bin \
  /private/WildArms/gpu/complete_ordered_gp0.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/after.u16le.bin \
  --require-post-match \
  > /private/WildArms/gpu/stage438-private-reconciliation.json
```

For diagnostic use without a strict failure exit, omit
`--require-post-match`. The machine-readable verdict may then be
`true`, `false`, or `null`; only `true` with a nonzero known-word
count is an internally consistent supported-subset result.

The SHA-256 in the pre-trace JSONL header is still only a consistency
check between files; there is no cryptographic emulator provenance,
source-game attestation, or verification of frame boundaries here.

## Relation to Surf Village original-style restoration

The original goal is to recover the genuine texture-page upload,
individual 4bpp CLUT row, STP/alpha behavior and geometry for one
visible roof or village well. A successful Stage438 conditional
reconciliation only eliminates some incorrect transfer models. It
does not certify the originally sampled CLUT, because the PS1
texture/cache behavior, GPU rasterization, scene provenance and
capture chronology remain unverified.

The next genuinely required input is an independently recorded
**original-game, complete ordered GP0 trace**, paired with
authentic initial/final VRAM from the same trace interval. No such
trace has been collected by this public code.

## Test/CI acceptance

`tests/test_audit_private_gp0_postframe_reconciliation.py` contains
13 synthetic-only regressions, including:

- full-memory exact and corrupted replay with zero draws;
- known-only comparison after a GPU drawing command;
- no-verdict outcome when all words are potentially changed;
- source-to-target VRAM copy knowledge transfer;
- source copy without recent known post-draw upload;
- postframe file geometry, strict-mode failure and privacy checks.

CI operates entirely on invented buffers and the earlier Stage437
synthetic packet fixtures. Never upload original BIN/CUE,
`CDSTG.BIN`, GP0 packet logs, raw VRAM dumps, screen captures,
derived assets or private report JSON to a public repository.
