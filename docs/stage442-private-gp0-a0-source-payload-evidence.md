# Stage442 — owner-private decoded CDSTG source → GP0(A0) payload evidence

## Purpose

Stage440 scans raw PS1 VRAM for long byte runs also present in a
bounded, WA1-LZSS-decoded CDSTG graphics stream. Stage441 narrows the
search to source runs covering a particular first UV texture word in
**modeled pre-draw VRAM**. Neither earlier comparison directly checks
what bytes the purported original GPU transfer command contained.

Stage442 checks the next independently falsifiable relationship:
**does one complete GP0(A0) CPU-to-VRAM packet include a sufficiently
long, byte-identical source run in its payload, at the packet's
declared destination coordinates?**

The answer is only conditional on the supplied ordered GP0 trace.
This tool does not capture, cryptographically attest or verify the
completeness of the trace. A match is *not* proof that the original
Wild Arms GPU actually received the packet or that a visible polygon
used the uploaded texture.

## Algorithm

- Inputs are Stage437's complete, independently acquired owner-private
  GPU packet sequence, an exact 1 MiB **pre-packet** PS1 VRAM snapshot,
  and the owner-private original `CDSTG.BIN` decoded using Stage426.
- The existing Stage441 bounded source index is reused. Only
  high-information 64-byte source anchors are eligible, rejecting
  repeated low-information blocks and anchors with more than 16
  candidate stream occurrences.
- Each GP0(A0) packet must have a valid rectangle, exact full image
  payload length and bounds within conventional 1024×512 VRAM.
  Original data halfwords are read as **little-endian**, row by row.
  One extra high halfword of the last GP0 word for odd pixel counts
  is ignored rather than treated as uploaded data.
- Source runs must start at a 64-byte boundary in a decoded source
  stream, but a match can begin at any packet-row offset whose
  **absolute destination X** is aligned to 16 PS1 u16 VRAM words.
  This supports packets with an unaligned starting destination.
- At least **three contiguous 64-byte blocks** (192 bytes) must be
  identical in sequence inside one transfer row. No matching
  sequence may cross the row boundary, borrow padding words or
  wrap around VRAM. The minimum is configurable for diagnostics.
- The report includes A0 packet index, destination X/Y, row index,
  source stream/graphics region and source/transfer offsets, length,
  counts, SHA-256 of the original-source run and effective payload.
  All source and packet bytes remain in private process memory.
- Event/report samples are bounded; aggregate counts include **all**
  A0 packets even once the sample cap has been reached. Repeated
  source streams produce separate ambiguous references rather than
  an unjustified unique source attribution.
- Existing Stage437/438 GP0 transfer/mask restrictions, Stage439 E2
  texture-window guards and Stage441 first-UV correlation remain
  unchanged and report separately.

## Private use

After the owner has privately extracted the actual `CDSTG.BIN`,
recorded VRAM **before** any GPU packets, and obtained a trustworthy,
complete ordered raw GPU transfer/draw trace:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/before.u16le.bin \
  /private/WildArms/gpu/complete-ordered-packets.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/after.u16le.bin \
  > /private/WildArms/gpu/stage442-private-a0-source-evidence.json
```

These are illustrative local paths. The PCSX-Redux REST screenshot
and paused VRAM endpoints do **not** provide a complete ordered GP0
packet exporter or an authenticated pre-packet snapshot.

The JSON adds `a0_source_payload_reports` and aggregate
`A0_SOURCE_BYTE_RUN_MATCHES` / `A0_PACKETS_WITH_SOURCE_RUNS` counters.
Absence of a run can be caused by tiling, swizzling, split uploads,
unaligned source offsets, transformed data, palette transfers,
fragmentation or the intentionally conservative filters. It is not
proof that the original texture was absent.

## Strict interpretation

The evidence hierarchy remains:
1. A source run equal to supplied A0 **packet payload bytes** is a
   stronger *conditional source→command relation* than a match only
   in final VRAM.
2. Neither match authenticates emulator trace provenance, timing or
   completeness, the loaded Wild Arms revision, or Surf Village.
3. The packet payload says nothing by itself about which visible
   roof, well, wall, sprite, 4bpp CLUT, STP mode, cached texture or
   source tile a GPU draw used.
4. Only genuine original emulator instrumentation, GP0+VRAM state
   verification, and comparisons with original visible game frames
   can support a source-grounded original-style HD restoration.

**Never upload** real disc images, CDSTG, raw VRAM, GP0 packet logs,
screenshots, decoded assets, derived artwork or private report hashes
to a public GitHub branch, CI artifact or release.

## Synthetic tests

`tests/test_audit_private_gp0_a0_source_payload.py` includes 22
synthetic-only tests covering full 192-byte runs, altered/short
payloads, A0 row boundaries, unaligned destinations, final legal
VRAM word, odd-pixel padding, repeated source ambiguity, sampling
caps, trace entrypoint integration, forward compatibility with the
earlier VRAM/UV analyzer and metadata-only reporting.

CI success only validates the conservative modeled algorithm with
invented packet words and streams. It does NOT mean genuine Wild Arms
graphics or an original emulator GP0 trace have been acquired.
