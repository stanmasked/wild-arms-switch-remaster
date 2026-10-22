# Stage444 — conservative GP0(80) copy-chain lineage of original A0 graphics

## Motivation

Stage443 records the exact GP0(A0) packet that directly wrote each
halfword of modeled PlayStation VRAM. It intentionally **invalidates
direct A0 attribution** for destinations of GP0(80) VRAM-to-VRAM copies.

Original games may upload a texture once and then relocate or duplicate
its VRAM region through GP0(80), without another A0 transfer. Ignoring
this may lose useful provenance; blindly declaring a copy equivalent to
a fresh A0 may invent source attribution. Stage444 introduces an
**independent, strictly conditional transitive lineage**, without
changing Stage443's direct-writer semantics.

## What is tracked

`tools/audit_private_a0_transitive_copy_lineage.py` maintains three
parallel arrays for every one of the **524,288 u16 words** in PS1
1024×512 VRAM:

- **Original A0 packet index** from the supplied ordered GP0 trace;
- **Original destination word address** of that particular A0;
- **Copy hop count** from that original A0, beginning at zero.

Each modeled valid A0 transfer sets all three fields for its exact
destination words. Each nonoverlapping GP0(80) copies the source
metadata, incrementing the hop count, with a snapshot-before-write
algorithm. Unknown origins remain unknown; no original pretrace VRAM
word is falsely assigned a writer. Overlapping or wrapping copies
remain unsupported and are rejected by the existing replay layer.

The parent Stage443 direct-author array is separately invalidated
at every GP0(80) destination. **Transitive origin is never reported
as a direct A0 write at the copied location.**

## Source-run confidence at a later 4bpp textured draw

When Stage439 can decode the first declared UV (texture window E2
explicitly zero), the new `first_uv_transitive_a0_copy_lineage`
diagnostic:

1. Finds the traced A0 packet and **original word address** from
   the modeled first-UV location, or states that the origin is unknown.
2. Looks only at source runs which Stage442 matched **inside the
   payload of that exact original A0 packet**. The unknown/oversized
   source-run sampling case remains explicitly inconclusive.
3. Locates the expected present-day run by the difference between
   original run start and the UV's original word address.
4. Requires **every consecutive halfword** in the full matched run
   to retain both the *same A0 packet* and the *exactly increasing
   original A0 address*. A fragment, dropped/swapped half, wrong row
   or overwritten word cannot validate the whole run. A run may be
   legitimately reconstructed by multiple ordered nonoverlapping
   copies if all original halfwords remain contiguous.
5. Checks Stage437's independent draw epochs across that entire
   surviving run; any earlier unmodeled GPU rasterization blocks
   a fresh-data claim until the words have actually been uploaded
   again. Merely copying stale words does not restore freshness.
6. Reports source stream ordinal/offset, original A0 packet, original
   and current VRAM word coordinates, copy hop range, matching
   whole-run count and freshness. It never exports raw VRAM, GPU
   words, palette values or decoded graphics.
7. Counts every modeled draw even if the JSON event detail cap is
   exceeded. Duplicate source-stream matches remain separate
   alternatives rather than an asserted unique attribution.

Potential states include
`CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN`,
`TRANSITIVE_SOURCE_RUN_WITH_UNVERIFIED_FRESHNESS`,
`PARTIAL_OR_REORDERED_SOURCE_RUN_NOT_PROVEN`,
`A0_ORIGIN_WITH_NO_MATCHED_SOURCE_RUN_AT_UV`,
`SOURCE_MATCH_SAMPLES_TRUNCATED`,
`NO_KNOWN_A0_ORIGIN_FOR_FIRST_UV`, and
`FIRST_UV_UNAVAILABLE_FOR_COPY_LINEAGE`.

The word **conditional** is essential: the input GP0 stream
has not been authenticated as a real original-game trace.

## Private operator workflow

Use the Stage437–443 entrypoint unchanged; Stage444's additional
fields are generated automatically when private decoded CDSTG
streams were supplied:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/before-gp0.u16le.bin \
  /private/WildArms/gpu/complete-gp0-packets.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/after-gp0.u16le.bin \
  > /private/WildArms/gpu/stage444-private-lineage.json
```

These paths are illustrative. This stage has not extracted the
owner's full 637 MB source disc or recorded authentic GP0 commands.
The screenshot and paused VRAM REST capture of PCSX-Redux does
not independently provide the complete ordered GP0 stream required
for proof.

The original disc, CDSTG source graphics, VRAM snapshots, GPU packet
traces, private JSON reports and derived images must not enter public
GitHub or GitHub Actions.

## Limits of current modeling

- GP0(80) copy source coordinates are trusted only *inside* the
  validated synthetic/private trace. We still need authentic emulator
  packet capture and matching pre-/post-packet VRAM.
- The renderer does not rasterize drawing commands. When a draw
  occurs, the modeled copy chain can still preserve **provenance
  labels**, but no longer proves the GPU really retained the source
  pixel values. Draw-epoch freshness records this uncertainty.
- This does not model texture/CLUT caches, GPU bit15/STP,
  polygon rasterization, clipping, coordinates of visible original
  Surf Village geometry or the original game's scene identity.
- A matched source run must fit into a single 1024-word VRAM row.
  Nonlinear texture layouts, rearranged chunks and non-grid source
  patterns may be true uploads but intentionally remain unrecognized.
- A green CI only proves these conservative rules against
  ROM-free, synthetic image and GP0 packet fixtures, not actual
  PlayStation hardware observations or restored commercial art.

## Tests and acceptance

`tests/test_audit_private_a0_transitive_copy_lineage.py`
covers direct versus transitive distinction, one/two/mixed copy
hops, fragmented/reordered runs, partial and UV-word overwrites,
intervening draws, reupload, repeated ambiguous source streams,
texture-window uncertainty, source sample truncation, copy bounds,
event caps, private-entrypoint integration and privacy.

Mark the PR ready for review only when Host Core, Disc analysis and
Matrix audits all pass on the **same final commit**. The next
authentic milestone is unchanged: use the owner's original complete
Wild Arms disc, a synchronized original-game GP0 capture and
a verifiable Surf Village screenshot to prove visible texture
assignment before claiming a successful remake scene.
