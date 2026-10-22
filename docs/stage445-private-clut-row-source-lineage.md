# Stage445 — CLUT palette-row A0/GP0(80) provenance beside the textured first UV

## Why this stage matters

Stages439–444 investigate how the first declared UV of a modeled PS1
4bpp draw points into VRAM and which *original-source stream* could have
been loaded, directly or through later GP0(80) copies. **The palette
may have been uploaded or copied separately from the texture.**
A byte-exact 4bpp texture source alone does not establish the CLUT
selected by the original GPU.

Stage445 therefore independently checks, at the **modeled pre-draw
instant**, the selected CLUT entry and the full 16-halfword CLUT row.
This is a conditional memory/provenance audit, not GPU rasterization,
cache emulation or an original Surf Village image.

## Implementation

- `tools/audit_private_gp0_texture_first_uv.py` records the
  *declared U coordinate's nibble position within its 16-bit texture
  word* (0–3), which is distinct from the **4-bit palette index
  read from that modeled texture word**. No source color/index word
  is placed in the resulting metadata.
- `tools/audit_private_gp0_clut_row_origin.py` verifies that
  the selected halfword SHA-256 agrees with Stage439's independently
  computed hash; a mismatch is a hard error rather than silently
  accepting inconsistent evidence.
- The existing Stage437 candidate row map is used for exact
  **32-byte/16-color CLUT row** equality against privately decoded
  original CDSTG candidate banks. Duplicate candidate banks/rows
  remain separate alternatives.
- Stage444's transitive word-origin arrays determine whether all
  16 palette halfwords still originate from the **same GP0(A0)
  packet and consecutive original source VRAM word addresses**,
  allowing proven nonoverlapping GP0(80) copy chains.
- Per-word draw-epoch accounting is used separately to determine
  whether the complete CLUT row was explicitly refreshed since the
  last GPU drawing command. Mixed origin, partial copies, an
  intervening draw, or a baseline-only row cannot earn the
  stronger **fresh candidate row** status.
- The selected CLUT halfword A0 packet index and the selected
  texture halfword A0 packet index are reported **independently**.
  These may refer to different packets; their equality is
  diagnostic only, and is *not* proof of actual hardware sampling.
- When the GP0(E2) texture-window state is unobserved or nonzero,
  the first-UV texture index cannot be modeled by this subset.
  The selected CLUT *entry* is **not guessed**.
- A candidate row match is a statement about modeled VRAM bytes,
  not proof that the GPU had sampled this row through its real CLUT
  or texture caches; bit15/STP, clipping and visible framebuffer
  colors remain unmodeled.

The private JSON event field is `first_uv_clut_row_origin`. Its
diagnostics distinguish:

- `CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN`
- `CANDIDATE_CLUT_ROW_ORIGIN_WITH_UNVERIFIED_FRESHNESS`
- `CANDIDATE_ROW_WITH_PARTIAL_OR_MIXED_A0_ORIGINS`
- `CANDIDATE_ROW_WITHOUT_KNOWN_A0_ORIGIN`
- `NO_DECODED_SOURCE_PALETTE_ROW_MATCH`
- `FIRST_UV_UNAVAILABLE_CLUT_ENTRY_NOT_EVALUATED`

Detailed JSON samples respect Stage437's event cap, but the CLUT
origin status counters consider **every modeled 4bpp draw**.

## Owner-private reproduction

Use the same existing entrypoint as Stages437–444, **only** after
obtaining a private complete GP0 command stream synchronized with
its precise before-first-packet raw PS1 VRAM snapshot. The 637 MB
original Wild Arms BIN and decoded CDSTG bytes are not available
inside this public CI and must never be uploaded there:

```sh
python tools/audit_private_gp0_upload_timeline.py \
  /private/WildArms/extracted/CDSTG.BIN \
  /private/WildArms/gpu/prepacket.u16le.bin \
  /private/WildArms/gpu/complete-ordered-gp0.jsonl \
  --map-index 2 \
  --post-vram /private/WildArms/gpu/postpacket.u16le.bin \
  > /private/WildArms/gpu/stage445-clut-origin-private.json
```

All paths are illustrative, not evidence of completed capture.
Do **not** commit original BIN/CUE, CDSTG, decoded source data,
VRAM, GPU packet data, original screenshot, derived artwork, or
even SHA-256-based owner-private reports to the public repository.

## CI and remaining proof gates

`tests/test_audit_private_gp0_clut_row_origin.py` covers real
arithmetic against entirely **synthetic** 4bpp image words and
candidate palette banks: whole-row fresh A0 uploads, transitive
GP0(80) palette copies, duplicate banks, mixed or partially
overwritten rows, stale memory after drawing, baseline-only row,
unknown/nonzero E2, hash mismatch rejection, event cap counters
and private entrypoint compatibility.

A green test suite proves only **consistent accounting** in this
modeled subset. No original Surf Village screenshot or synchronized
original-game GP0 trace has been captured in this stage. Therefore
no claim is made that a particular well/roof texture, placement,
palette or rendered color has yet been restored.

The next evidence gate should prioritize **capturing authentic GPU
commands** rather than relying indefinitely on synthetic packet
data, then connecting observed texture/CLUT origins to a real
PCSX-Redux screen-space crop and matching rendered candidate.
