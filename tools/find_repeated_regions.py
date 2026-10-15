#!/usr/bin/env python3
"""Inventory exact repeated 2048-byte-aligned regions in a PS1 ISO file.

Read-only. Emits offsets and lengths only; never exports source game bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"

def read_iso_form1(image, entry, limit=2_000_000):
    size = entry["size"]
    if size < 0 or size > limit:
        raise ValueError("file size exceeds read-only audit cap")
    blocks = []
    with open(image, "rb") as stream:
        for i in range((size + 2047) // 2048):
            stream.seek((entry["lba"] + i) * 2352)
            sector = stream.read(2352)
            if len(sector) != 2352 or sector[:12] != SYNC:
                raise ValueError("bad sync")
            if sector[15] != 2 or sector[18] & 0x20 or sector[16:20] != sector[20:24]:
                raise ValueError("not MODE2/Form1")
            blocks.append(sector[24:2072])
    return b"".join(blocks)[:size]

def matching_regions(data, block_size=2048, min_blocks=6):
    if block_size < 1 or min_blocks < 1:
        raise ValueError("invalid block size")
    count = len(data) // block_size
    hashes = [hashlib.sha256(data[i*block_size:(i+1)*block_size]).digest()
              for i in range(count)]
    by_hash = {}
    for i, h in enumerate(hashes):
        by_hash.setdefault(h, []).append(i)
    seen = set()
    found = []
    for a, h in enumerate(hashes):
        for b in by_hash[h]:
            if b <= a or (a, b) in seen:
                continue
            length = 0
            while a+length < b and b+length < count and hashes[a+length] == hashes[b+length]:
                length += 1
            for k in range(length):
                seen.add((a+k, b+k))
            if length >= min_blocks:
                found.append({"offset_a": a*block_size, "offset_b": b*block_size,
                              "common_bytes": length*block_size,
                              "delta": (b-a)*block_size})
    found.sort(key=lambda row: (-row["common_bytes"], row["offset_a"], row["offset_b"]))
    return found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("disc")
    parser.add_argument("inventory", help="JSON from inspect_disc.py --json")
    parser.add_argument("--path", default="/BIN/CDEF.BIN;1")
    parser.add_argument("--min-blocks", type=int, default=6)
    args = parser.parse_args()
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    entries = [e for e in inventory["entries"] if e["path"] == args.path and not e["directory"]]
    if len(entries) != 1:
        parser.error("target ISO file not found")
    data = read_iso_form1(args.disc, entries[0])
    print(json.dumps({"path": args.path, "bytes_analyzed": len(data),
                      "block_size": 2048,
                      "regions": matching_regions(data, min_blocks=args.min_blocks)}, indent=2))

if __name__ == "__main__":
    main()
