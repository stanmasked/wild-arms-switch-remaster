# Stage408 — CDFLR candidate pointer-table evidence

## Source and privacy boundary

The source is the **private, user-provided Wild Arms USA PlayStation image**. `CDFLR.BIN` was extracted by validating its catalogued raw CD sector extent. The container remains outside the public repository; this note contains **metadata only**, not original program, graphics, audio or story content.

## Direct observations from the first 256 bytes

- `CDFLR.BIN` has 15,917,056 bytes. Its source SHA-256 is recorded privately.
- Its first **58** little-endian 32-bit words are strictly increasing, four-byte-aligned and within the PS1 KSEG0 2 MiB RAM address range.
- Word **58** is zero; the unused portion of the 256-byte header is also zero (**24 padding bytes** after 232 table bytes).
- The candidate base `0x80183000` translates the first pointer to file offset `0x100`, precisely after the aligned table.
- With this *candidate* mapping, all 58 targets lie inside the 15,917,056-byte file. The last target is at offset `0x35110` (217,360 decimal).
- There are 57 positive word-aligned adjacent spans, from **4** to **61,796** bytes. The last target's length is not established.
- **39** targets, indices **2–40**, have a first little-endian word of `0x41` (65 decimal). No meaning is assigned to this field.

These observations are internally coherent with a RAM-relocated pointer table into an early section of the file. The chosen base is **hypothetical**: it is inferred from the 256-byte boundary and is not yet proven by the original loader. These values do **not** prove that any entries represent field maps, textures, sprites, events, or playable content.

## Independent executable-literal cross-check

From the actual PlayStation disc, `EXE/WILDARMS.EXE;1` (794,624 bytes)
contains **one aligned** 32-bit literal `0x80183000` in its text/data region
at file offset `0xC1B40` (793,408 decimal). It is within an adjacent group
of RAM-address-like words in the main executable, independent of the CDFLR
pointer-table prefix.

The optional `--executable /private/path/WILDARMS.EXE` option checks the
PS-X EXE header and declared text extent, scans it for a four-byte-aligned
candidate-base literal, and emits only match counts/file offsets. This is
stronger corroboration of the proposed address but **does not establish**
which loader function uses it, whether CDFLR is loaded there at runtime,
or whether any of the targets represent sprites/maps.

## Reproducible private verification

```sh
python tools/inspect_cdflr_pointer_table.py /private/path/CDFLR.BIN \
  --executable /private/path/WILDARMS.EXE \
  > /private/path/cdflr-pointer-evidence.json
```

The probe reads a bounded 256-byte table header and only four bytes at each candidate target. It also computes the full-file SHA-256 in chunks. The report includes counts, file offsets and flags, but **never prints source bytes or decoded assets**.

The public CI tests use only synthetic data and intentionally corrupted tables, including unsorted, misaligned, out-of-range and nonterminated pointers.

## Next acceptance gate

1. Confirm the pointer base from *independent* executable-loader code or a runtime memory trace, rather than only the 0x100 boundary.
2. Classify which target groups are tables, packed data, media or code by bounded structural checks. Record negative results.
3. Investigate the special CDSTG block **#25** separately: its 256-byte header and 2,048-byte windows do not resemble the 127 PS-X EXE-like records. The byte distribution is distinct, but that alone does not identify its format.
4. Recover one *verified* resource and compare a decoded output locally to an original emulator/reference capture. Only then begin scene integration.

Do not claim a recovered map or a decodable graphics format from this report alone. No PS1 bytes should be committed to GitHub.
