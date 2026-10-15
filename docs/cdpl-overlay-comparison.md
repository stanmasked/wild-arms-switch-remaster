# CDPL overlay comparison — verified observations

Using the user-supplied Wild Arms (USA) raw MODE2/Form1 disc image:

| Metric | CDPL00.BIN | CDPL01.BIN |
|---|---:|---:|
| ISO extent size, bytes | 212216 | 217448 |
| Leading 32-bit KSEG0-range words | 61 | 61 |
| Leading word sequence nondecreasing | Yes | Yes |
| Identical byte prefix between files | 132 bytes | 132 bytes |

The first 33 little-endian words match, and at byte offset 132 the
files diverge. A 61-word initial run of KSEG0-range addresses exists in
each file; the differing words after byte 132 may reflect scene-specific
load addresses or code/data variants. **This does not prove a file
format, module relocation table, resource offsets or the exact meaning
of the addresses.** Do not derive asset extraction boundaries from it.

Reproduce locally without distributing the image:

```sh
python3 tools/inspect_disc.py "Wild Arms (USA).bin" --json > inventory.json
python3 tools/compare_overlays.py "Wild Arms (USA).bin" inventory.json \
  "/BIN/CDPL00.BIN;1" "/BIN/CDPL01.BIN;1"
python3 -m unittest discover -s tests -p 'test_*.py'
```
