# Stage435 — extract owner's real Wild Arms CDSTG directly from one CUE/BIN track

## Why this is the next useful step

Stages426–434 created original-source Surf Village palette probes and
private GPU/VRAM/screenshot comparison infrastructure. But those stages
require a privately extracted `CDSTG.BIN` and an original running PS1
frame before any scene art can be called authentic.

For the owner's original Wild Arms (USA), Google Drive folder
`Wild Arms` was examined during development: it contains
`Wild Arms (USA).cue` and `Wild Arms (USA).bin`. The 81-byte CUE
declares **one `MODE2/2352` track with INDEX 01 at 00:00:00**.
Drive metadata reports a **637,163,856-byte** BIN, exactly
**270,903 sectors of 2352 bytes**. This is a *metadata plus CUE*
observation, not an independent content/hash verification of the
entire original BIN. The connector refused the 637 MB binary download
because the connection limits single files to 256 MiB. The original
BIN has therefore **NOT** been read or extracted in this stage.

Stage435 adds a **local-only owner-private extractor** that operates
on that full BIN on a computer where the disc file is already present.
It does not upload the disc or any original graphics into GitHub.

## Mode2/Form1 vs raw sectors

The CUE track is `MODE2/2352`, so physical sectors are 2352 bytes.
For CD-XA Mode2/Form1 ISO9660 filesystem sectors, the 2048-byte logical
data area begins at offset **24** into a raw sector. In raw Mode2/Form2,
the payload size and location have different semantics; this extractor
conservatively rejects Form2 in all sectors it needs.

References:
- PSX-SPX CD-ROM raw disc format:
  https://psx-spx.consoledev.net/dev/ps1/cdr/cdromformat/
- PSX-SPX CUE/BIN disk image structure:
  https://psx-spx.consoledev.net/dev/ps1/cdr/cdromfileformats/diskimages/

The extractor reads ISO9660 Primary Volume Descriptor (PVD) at logical
sector 16; checks `\x01CD001\x01`, ISO9660 both-endian directory
extent fields, directory bounds, and precisely one `CDSTG.BIN;version`.
A requested match must be exactly **128 × 0x91000 = 76,021,760 bytes**,
the known Wild Arms CDSTG geometry already used in Stages420–426.

Unsupported CUE multitrack layouts, alternate sector encodings,
malformed ISO metadata, multi-extent files, invalid subheaders, unsafe
CUE filenames and out-of-bounds ISO extents fail closed. This is not a
general-purpose ISO extractor and does not attempt to decompress or
render a tile.

## Owner-local procedure (private disk only)

Download the original two files `Wild Arms (USA).cue` and
`Wild Arms (USA).bin` from the owner's Google Drive folder directly
to the same **private local directory**. Do not rename the referenced
BIN without updating the private CUE accordingly, and do not put
game files into the public Git repository.

```sh
mkdir -p /private/WildArms/extracted

python tools/extract_private_cdstg_from_cue_bin.py \
    '/private/WildArms/disc/Wild Arms (USA).cue' \
    /private/WildArms/extracted

python tools/audit_surf_palette_rows.py \
    /private/WildArms/extracted/CDSTG.BIN \
    --map-index 2 > /private/WildArms/extracted/stage435-private-surf-report.json
```

Both paths are illustrative. The destination directory must exist.
The script extracts only `CDSTG.BIN`, in a no-clobber file created
with restrictive 0600 permissions, and emits a small JSON metadata
record with source raw-sector count, ISO location, 76,021,760-byte
length and SHA-256. It does not print original pixels, sector data,
CLUT color words or any decoded images.

**Do not publish the extracted file or private hashes** in GitHub,
Actions artifacts or Switch NRO releases. The original disc is
required only for private testing/asset generation.

## Proof status

- **Verified this session:** Google Drive folder and CUE format;
  user-owned BIN **size metadata only** (not its bytes or content hash).
- **Added to code:** bounded, single-track ISO9660 Mode2/Form1
  private extractor and ROM-free fixture regressions.
- **Not performed:** direct extraction from actual 637 MB BIN in this
  execution environment due to the connector's 256 MiB limit.
- **Not established:** original disc release identity by checksum,
  scene/CLUT placement, original GPU frame identity or a rendered
  Surf Village roof/well match.

The next authentic milestone remains an owner-local run of the
original game in PCSX-Redux and a Stage432 screenshot/VRAM witness,
then Stage433/434 exact screen-space comparison of a small landmark.
The extractor reduces dependence on a separately provided
`CDSTG.BIN` and preserves provenance from the original disc.
