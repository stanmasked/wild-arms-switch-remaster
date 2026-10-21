#!/usr/bin/env python3
"""Extract selected ISO9660 files from a raw Mode 2/2352 Wild Arms USA image.

The image and extracted resources must remain local/private. This utility
validates each raw sector before writing the 2048-byte Mode 2 Form 1 payload.
It is an extraction helper for the already catalogued extents, not a decoder
for the proprietary formats stored inside those files.
"""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

SECTOR_BYTES = 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MODE2 = 2
SUBHEADER_OFFSET = 16
SUBHEADER_BYTES = 4
USER_DATA_OFFSET = 24
USER_DATA_BYTES = 2048
FORM2_FLAG = 0x20
EXPECTED_IMAGE_BYTES = 637_163_856

# Extents from the previously generated ISO9660 directory-only catalog.
# LBA values are relative to the start of the Mode 2/2352 data track.
ENTRIES = {
    "CDSTG.BIN": {"lba": 1383, "size_bytes": 76_021_760},
    "CDFLR.BIN": {"lba": 38503, "size_bytes": 15_917_056},
}


def _read_mode2_form1_payload(source, lba):
    source.seek(lba * SECTOR_BYTES)
    sector = source.read(SECTOR_BYTES)
    if len(sector) != SECTOR_BYTES:
        raise ValueError(f"truncated raw sector at LBA {lba}")
    if sector[:12] != SYNC:
        raise ValueError(f"invalid sync pattern at LBA {lba}")
    if sector[15] != MODE2:
        raise ValueError(f"expected Mode 2 sector at LBA {lba}")
    first = sector[SUBHEADER_OFFSET:SUBHEADER_OFFSET + SUBHEADER_BYTES]
    second = sector[SUBHEADER_OFFSET + SUBHEADER_BYTES:SUBHEADER_OFFSET + 2 * SUBHEADER_BYTES]
    if first != second:
        raise ValueError(f"duplicated subheader mismatch at LBA {lba}")
    if first[2] & FORM2_FLAG:
        raise ValueError(f"Mode 2 Form 2 sector cannot hold ISO9660 2048-byte payload at LBA {lba}")
    payload = sector[USER_DATA_OFFSET:USER_DATA_OFFSET + USER_DATA_BYTES]
    if len(payload) != USER_DATA_BYTES:
        raise ValueError(f"truncated user data at LBA {lba}")
    return payload


def extract_entry(source_path, output_path, lba, size_bytes):
    """Extract one catalogued extent, writing atomically and returning metadata."""
    source_path = Path(source_path)
    output_path = Path(output_path)
    if type(lba) is not int or lba < 0:
        raise ValueError("lba must be a non-negative integer")
    if type(size_bytes) is not int or size_bytes <= 0:
        raise ValueError("size_bytes must be a positive integer")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_path}")
    source_size = source_path.stat().st_size
    sector_count = (size_bytes + USER_DATA_BYTES - 1) // USER_DATA_BYTES
    end_offset = (lba + sector_count) * SECTOR_BYTES
    if end_offset > source_size:
        raise ValueError("catalogued extent exceeds source image bounds")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".partial",
                                           dir=str(output_path.parent))
    digest = hashlib.sha256()
    remaining = size_bytes
    try:
        with os.fdopen(fd, "wb") as target, source_path.open("rb") as source:
            for sector_index in range(sector_count):
                payload = _read_mode2_form1_payload(source, lba + sector_index)
                chunk = payload[:min(remaining, USER_DATA_BYTES)]
                target.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            target.flush()
            os.fsync(target.fileno())
        if remaining != 0:
            raise ValueError("internal extraction length mismatch")
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise

    return {
        "name": output_path.name,
        "lba": lba,
        "size_bytes": size_bytes,
        "sectors_validated": sector_count,
        "sha256": digest.hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="local raw Mode 2/2352 Wild Arms USA BIN")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="private local output directory; existing target files are not overwritten")
    parser.add_argument("--entries", nargs="+", choices=sorted(ENTRIES), default=sorted(ENTRIES),
                        help="catalogued files to extract (default: CDSTG.BIN CDFLR.BIN)")
    args = parser.parse_args()

    image_size = args.image.stat().st_size
    if image_size != EXPECTED_IMAGE_BYTES:
        parser.error(
            f"unexpected image size {image_size}; expected {EXPECTED_IMAGE_BYTES} bytes for "
            "the currently catalogued Wild Arms (USA).bin. Verify the image/catalog before extraction."
        )

    targets = [args.output_dir / name for name in args.entries]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        parser.error("refusing to overwrite existing output(s): " + ", ".join(existing))

    results = []
    for name in args.entries:
        entry = ENTRIES[name]
        results.append(extract_entry(args.image, args.output_dir / name,
                                     entry["lba"], entry["size_bytes"]))

    print(json.dumps({
        "schema": 1,
        "kind": "WILD_ARMS_MODE2_FORM1_EXTRACTION",
        "source_name": args.image.name,
        "source_size_bytes": image_size,
        "sector_bytes": SECTOR_BYTES,
        "user_data_bytes_per_sector": USER_DATA_BYTES,
        "outputs": results,
        "original_payload_exported_to_stdout": False,
        "format_decoding_claimed": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
