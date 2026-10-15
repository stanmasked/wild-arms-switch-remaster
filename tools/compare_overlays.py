#!/usr/bin/env python3
"""Compare two raw MODE2/Form1 ISO9660 file extents without extracting assets."""
import argparse
import json

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"

def read_prefix(disc, entry, limit=4096):
    length = min(entry["size"], limit)
    data = bytearray()
    for index in range((length + 2047) // 2048):
        disc.seek((entry["lba"] + index) * 2352)
        sector = disc.read(2352)
        if len(sector) != 2352 or sector[:12] != SYNC:
            raise ValueError("invalid CD sector sync")
        if sector[15] != 2 or sector[18] & 0x20:
            raise ValueError("sector is not MODE2/Form1")
        data.extend(sector[24:2072])
    return bytes(data[:length])

def common_prefix(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))

def leading_pointer_run(data):
    values = [int.from_bytes(data[i:i+4], "little") for i in range(0, len(data)-3, 4)]
    found = []
    for value in values:
        if not 0x80000000 <= value < 0x80200000:
            break
        found.append(value)
    return {"count": len(found),
            "nondecreasing": all(a <= b for a, b in zip(found, found[1:]))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("inventory", help="Output of inspect_disc.py --json")
    parser.add_argument("file_a", help="Exact ISO path including ;1")
    parser.add_argument("file_b", help="Exact ISO path including ;1")
    parser.add_argument("--limit", type=int, default=4096)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1024*1024:
        parser.error("--limit must be between 1 and 1048576")
    entries = {e["path"]: e for e in json.load(open(args.inventory))["entries"]
               if not e["directory"]}
    with open(args.image, "rb") as disc:
        a = read_prefix(disc, entries[args.file_a], args.limit)
        b = read_prefix(disc, entries[args.file_b], args.limit)
    print(json.dumps({"file_a": args.file_a, "file_b": args.file_b,
                      "bytes_compared": min(len(a), len(b)),
                      "identical_prefix_bytes": common_prefix(a, b),
                      "a_pointer_run": leading_pointer_run(a),
                      "b_pointer_run": leading_pointer_run(b)}, indent=2))

if __name__ == "__main__":
    main()
