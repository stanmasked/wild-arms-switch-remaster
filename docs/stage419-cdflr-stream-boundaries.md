# Stage419 — CDFLR marker and encoded-boundary audit

## Real original evidence

The user's private Wild Arms (USA) PlayStation image contains CDFLR.BIN,
partitioned into 67 fixed slots of 0x3A000 bytes. Every slot has 58
ordered KSEG0-RAM-like pointers and 24 **opaque** header bytes after them.
The opaque bytes are not required to be zero.

Each slot has eight data-like regions at pointer indexes 43,45,47,49,51,53,55,57.
All **536/536** begin with the little-endian u32 value **0x00008000**.

Only the first seven regions in each slot have a following pointer: 469
known-bounded regions in total. The last region #57 has no next pointer,
so the slot end is merely a maximum possible endpoint, **not** its verified
encoded length.

| Pointer region | Min span (bytes) | Max span (bytes) | End established? |
| --- | ---: | ---: | --- |
| 43 | 4,160 | 28,792 | Next pointer |
| 45 | 3,904 | 24,688 | Next pointer |
| 47 | 11,392 | 11,392 | Next pointer |
| 49 | 9,188 | 9,188 | Next pointer |
| 51 | 10,544 | 10,544 | Next pointer |
| 53 | 12,116 | 12,116 | Next pointer |
| 55 | 10,932 | 10,932 | Next pointer |
| 57 | 10,600 | 58,592 | **Slot end only (upper bound)** |

Every one of the 469 next-pointer-bounded spans is 4-byte-aligned and
shorter than 0x8000 (32,768) bytes. But the last-region slot-end upper bound
is larger than 32,768 in **27 of 67 slots**. This makes it unsafe to treat
every slot's entire last region as one 32 KiB stream.

## Narrow codec hypothesis test — negative evidence

The leading 0x8000 may suggest a 32KiB output size, but that interpretation
is NOT independently verified. To detect a common false lead, a simple
LSB-first flag-token sizing grammar was tested against the 469 bounded
regions:

- Skip four bytes as a *candidate*, not proven, header.
- Consume a flag byte, low bit first.
- A set flag consumes one literal byte and hypothetically produces one byte.
- A clear flag consumes two reference bytes and hypothetically produces
  (upper nibble of the second reference byte) + 3 bytes.
- Try to produce exactly 0x8000 bytes with at most 3 trailing encoded bytes
  allowed for alignment.

This heuristic does not check dictionary references or produce decompressed
bytes. The result on the original source was:

| Heuristic result | Regions |
| --- | ---: |
| Truncated before 32KiB hypothetical output | **131** |
| Reaches 32KiB with too much trailing encoded data | **338** |
| Reaches 32KiB at allowed boundary | **0** |
| Total next-pointer-bounded regions | **469** |

The result rejects **this exact simplistic flag-token grammar and
boundary requirement** as a universal decoder. It does NOT rule out other
LZSS variants, RLE, multiple chunks, transformed bytes, or different
output lengths. The last #57 regions are excluded from this boundary test,
since their real encoded endpoints are unknown.

## Reproduce privately

    python tools/audit_cdflr_stream_boundaries.py /private/CDFLR.BIN > /private/stage419-streams.json
    python -m unittest discover -s tests -p test_audit_cdflr_stream_boundaries.py

The public analyzer reports metadata, sizes, counts and error indices only.
No original bytes, decoded graphics, audio, game script, screenshots or raw
RAM data enter GitHub or CI. Tests use artificial synthetic inputs only.

## Next evidence gate

Identify actual game-code consumers of the 0x8000-prefixed sections or obtain
a genuine reference emulator memory trace. Independently verify the codec,
dimension/stride, ending conditions and PS1 CLUT relationships (including
exceptional blocks #4 and #28) before claiming a decoded original image
or beginning private texture import into the Nintendo Switch field engine.
