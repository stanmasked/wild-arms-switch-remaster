# Stage406: local PS1 container probe

This tool is a **metadata-only aid**, not a decoder. Run it only against a user-owned local copy of an extracted file. Never commit the disc image, extracted resources, probe JSON, screenshots, or logs containing original assets.

## Commands

Use a prefix sample to compare with the earlier 256-byte header-probe report:

```sh
python tools/probe_container.py /private/path/CDSTG.BIN --layout prefix --sample-bytes 256
python tools/probe_container.py /private/path/CDFLR.BIN --layout prefix --sample-bytes 256
```

The returned `sample.sha256` hashes exactly the sampled prefix and can be compared locally with the prior report's `header_sample_sha256`. The tool does not output the bytes themselves.

For a machine-readable comparison against the saved private header-probe report, save each prefix report locally, then run:

```sh
python tools/probe_container.py /private/path/CDSTG.BIN --layout prefix --sample-bytes 256 > /tmp/cdstg-prefix.json
python tools/probe_container.py /private/path/CDFLR.BIN --layout prefix --sample-bytes 256 > /tmp/cdflr-prefix.json
python tools/compare_container_probe.py /private/path/wild_arms_ps1_resource_probe.json /tmp/cdstg-prefix.json /tmp/cdflr-prefix.json
```

The comparator checks canonical filename, file size, prefix sample length and prefix SHA-256. It exits nonzero if any report differs or has no matching reference entry. The reference report should stay private and be obtained from the existing local project record; it is not committed to the repository.

Use distributed windows to gather a broader first look at each candidate:

```sh
python tools/probe_container.py /private/path/CDSTG.BIN --layout distributed --sample-bytes 8388608 > /tmp/cdstg-probe.json
python tools/probe_container.py /private/path/CDFLR.BIN --layout distributed --sample-bytes 8388608 > /tmp/cdflr-probe.json
```

The default budget is 1 MiB; the hard maximum is 8 MiB. Distributed mode samples up to eight 4-byte-aligned windows spread across the file. SHA-256 of the full file is computed in streaming chunks, so the entire file is never loaded into memory.

## Reading the report

- `file_size_bytes` and the whole-file `sha256` identify the exact input copy.
- `sample.windows` lists sampled offsets and lengths; `sample.sha256` hashes their concatenation in report order.
- Entropy and zero-byte fraction describe only the selected sample windows, not the entire file.
- `pointer_like_words` are repeated aligned little-endian values that fall within file bounds. They are candidates for further analysis, **not proven offsets or evidence of a specific format**.
- A lack of candidates does not prove that a file has no offset table; the relevant structures may be outside the sampled windows or use a different encoding.

## Safety and acceptance boundary

- No raw bytes or decoded assets are emitted by this tool.
- CI uses synthetic byte fixtures only.
- A probe report is not a decoded archive, image, map, or event script.
- Before designing a decoder, compare the prefix hash against the prior private metadata report, then gather additional independent evidence (repeated table layout, valid in-file ranges, and successful bounded decoding of known structures).
- Keep reports under a private local path such as `/tmp`; do not upload them as public artifacts.
