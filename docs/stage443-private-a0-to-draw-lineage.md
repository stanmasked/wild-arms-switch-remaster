# Stage443 — conditional direct A0 packet → modeled first-UV source lineage

## Why Stage442 is not enough

Stage442 recognizes an exactly matching decoded CDSTG source run inside a
GP0(A0) transfer payload. Stage441 independently recognizes a run covering
the texture halfword addressed by a modeled GP0 first-UV event. Neither
result alone links **the precise packet that last wrote that word** to
the **later draw packet** in a single ordered GPU timeline.

Stage443 adds that missing conditional packet-index lineage. It
distinguishes newly uploaded A0 words from baseline VRAM, words overwritten
by a later A0, and words moved by a GP0(80) VRAM copy.

## Algorithm

`tools/audit_private_a0_draw_uv_lineage.py` maintains a private
array of **524,288 u16-word writer indices** for the modeled PS1
1024×512 VRAM. Each accepted GP0(A0) packet is assigned its actual
zero-based index in the ordered trace:

- Every destination halfword receives this exact packet index.
- Stage442's direct byte-identical 64-byte-block run matches are attached
  to the packet index, with candidate CDSTG stream ordinal and source
  offset. Up to 256 source run samples per packet are retained for
  coverage analysis; a truncated sample set explicitly remains
  **inconclusive**, never a definitive absence of source matching.
- On any GP0(80) copy destination, the **direct A0 writer** is
  invalidated. The original A0 origin may still be related through a
  blit, but that would require a separately proven transitive lineage.
  Stage443 refuses to assert it.
- At each supported Stage439 4bpp textured draw, the first UV is probed
  only when the GP0(E2) texture window has explicitly been set to zero.
  The current writer index of the UV halfword is inspected.
- A candidate matched run must contain the **whole first-UV halfword**
  and belong to that writer packet. This is a narrower statement than
  merely finding matching bytes in the same VRAM.
- The entire matched span is scanned for subsequent packet overwrites.
  The Stage437 draw epoch is also checked across every halfword: any
  intervening GPU draw, whose framebuffer writes are **not modeled**,
  blocks the fresh-run confidence flag until all run words are written
  again.
- Source candidates can be ambiguous; identical decoded source bytes
  from different graphics streams are reported as separate alternatives.
- All events are evaluated, even if only a bounded subset is included
  in the detailed JSON sample. Aggregate counters remain complete.

The result distinguishes these states:

`CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV`,
`A0_SOURCE_RUN_COVERS_UV_BUT_FRESHNESS_UNVERIFIED`,
`A0_WRITER_WITHOUT_MATCHED_SOURCE_RUN_AT_UV`,
`NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD`,
`A0_SOURCE_MATCH_SAMPLES_TRUNCATED_CANNOT_EXCLUDE_LINK`, and
`FIRST_UV_NOT_AVAILABLE_FOR_A0_ATTRIBUTION`.

A "fresh" result still means only that the **modeled ordered input**
has the indicated direct writer/byte relation. It **does not prove**
the original game emitted the supplied trace, that the GP0 commands
were executed at the asserted frame, or that its GPU read those
values through the real texture/CLUT caches.

## Private execution

This feature extends the existing Stage437–442 entrypoint; no new
original-source asset export is needed:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/initial-before-packets.u16le.bin \
  /private/WildArms/gpu/complete-ordered-gp0.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/after-packets.u16le.bin \
  > /private/WildArms/gpu/stage443-owner-private.json
```

These are **illustrative paths**, not evidence that original assets
were captured. The original Wild Arms 637 MB BIN was not downloaded
from Google Drive through this connector's 256 MiB limit, and no
authentic Surf Village GP0 command sequence with synchronized
pre-/post-VRAM has been captured in the current session.

Stage443 does not contain ROMs, disc files, pixel buffers, GP0 packets
or original texture data. However, packet indices, source offsets and
small hashes may be privacy/copyright-sensitive, so owner-generated
JSON reports must also remain **outside public GitHub/CI**.

## Interpretation and remaining gates

A direct A0 packet→source run→modeled first UV link is stronger
conditional evidence than a post-frame VRAM occurrence alone.
It is **still not** a verified Surf Village roof, well, texture page,
field tile, CLUT row, transparent pixel or rendered frame.

The outstanding independent prerequisites are:

1. Full owner-local extraction of original disc resources (Stage435/436).
2. An authentic, complete GPU packet trace synchronized with a verified
   **before-first-packet** VRAM capture and optional postpacket capture.
3. Proof of relevant original game/map and camera state, not only
   user-selected scene labels.
4. Verification of visible geometry, texture window, bit15/STP and
   PS1 cache semantics, followed by a real screenshot comparison
   against an original frame (Stages432–434).

## Synthetic CI

`tests/test_audit_private_a0_draw_uv_lineage.py` contains 22
ROM-free checks for A0 packet attribution, overlapping subsequent
writes, ambiguous source streams, copy invalidation, draw-epoch
staleness, source sample truncation, E2 uncertainty, backward
compatibility, private entrypoint integration and metadata-only
results.

A green test suite proves the **supported subset** of the memory
accounting model, not original game's GPU behavior or completed
original-style HD art.
