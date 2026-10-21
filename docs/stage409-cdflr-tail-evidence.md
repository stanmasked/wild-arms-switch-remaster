# Stage409 — CDFLR tail pair structural audit

## Private source

The original `CDFLR.BIN` (15,917,056 bytes) was extracted privately from the user's verified Wild Arms (USA) raw Mode 2/2352 image. Original file contents remain outside the public repository and Actions artifacts. The pointer-table address base `0x80183000` is still inferred, not proven from loader execution.

## Evidence (metadata only)

At the tail of the previously observed 58-entry pointer table:

- Entries **42, 44, 46, 48, 50, 52, 54, 56** each have an exactly **512-byte** span to the following pointer.
- Each 512-byte span can be interpreted as **256 little-endian 16-bit words**; the number of distinct words ranges from **28 to 174** across these eight spans.
- Entries **43, 45, 47, 49, 51, 53, 55, 57** all start with little-endian u32 value **`0x00008000`**.
- The seven known (next-pointer-bounded) odd-index spans range from **9,188** to **19,160** bytes.
- Entry **57 has no following pointer**, so its true resource end and resource length are **not known**; it is unsound to call the remaining bytes of the container one image or record.

The precise alternating pattern is compatible with **candidate 256-color palette-sized blocks followed by variable-length data**. No actual pixel encoding, color lookup convention, transparency semantics, compression scheme or image width/height has been proven. The full CDFLR container size must not be used as an implied bound for entry #57.

## Reproduction on private files

```sh
python tools/audit_cdflr_tail_pairs.py /private/path/CDFLR.BIN > /private/path/cdflr-tail-audit.json
```

The audit reads a bounded pointer-table header, eight 512-byte candidate palettes and the four-byte prefix of each paired data region. It emits record indices, counts, length summaries and flags, **not** the original words, decoded images or bytes.

All CI fixtures are synthetic. Negative controls deliberately alter pointer order, a palette-sized span and a paired data prefix. A failed pattern check is reported explicitly, never silently declared to be a palette.

## Next acceptance gates

1. Independently establish the candidate RAM base from actual loader/control-flow references, not just literal matches and a plausible `0x100` boundary.
2. Determine whether the 512-byte blocks are genuine PS1 CLUTs by cross-checking a bounded image decoder against a faithful PS1 reference frame.
3. Verify where the final data region ends before attempting full extraction.
4. Only after visually and structurally confirming a known game resource, integrate into the private original-style asset pipeline and Nintendo Switch field engine.
