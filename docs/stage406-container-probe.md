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


## Extract the two catalogued files from the Google Drive image

The connected Drive folder contains `Wild Arms (USA).bin` (637,163,856 bytes) and `Wild Arms (USA).cue`. The cue identifies the track as `MODE2/2352`. The connector's raw-file download limit is 268,435,456 bytes, so it cannot materialize the full BIN directly into this runtime. Do not publish the disc image to GitHub.

If you can download the BIN from Drive to a trusted local machine, this helper extracts only the two previously catalogued ISO9660 extents:

```sh
python tools/extract_wild_arms_iso_files.py "/private/path/Wild Arms (USA).bin" \
  --output-dir "/private/path/wildarms-extracted"
```

The current catalog expects the exact image size of 637,163,856 bytes and refuses a different size rather than silently applying stale extents. Each raw sector is validated for sync bytes, Mode 2, matching duplicated subheaders and Form 1 (not Form 2) before its 2048-byte user-data payload is written. Output files are written atomically; existing outputs are not overwritten.

Expected outputs:
- `CDSTG.BIN` — 76,021,760 bytes, LBA 1383, 37,120 sectors.
- `CDFLR.BIN` — 15,917,056 bytes, LBA 38503, 7,772 sectors.

The two extents are adjacent in the catalog (the first ends at LBA 38503, where the second begins). The tool emits only sizes, sector counts and SHA-256 hashes to stdout; it does not print asset bytes. Keep the output directory and report private. Upload just the two extracted files to the same private Drive folder (or attach them to this conversation) so they can be inspected here; both are below the connector's raw-file size limit. Successful extraction validates sector/container handling, not the proprietary formats inside the files.

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
