#!/usr/bin/env python3
"""Read-only candidate PS1 KSEG0 pointer-run inspection for raw MODE2/Form1 disc files.

This tool reports *candidates*, not verified archive indices. Input is a
user-owned BIN image and JSON inventory from inspect_disc.py.
"""
import argparse
import json

def read_payload(image, lba, size, cap=2048):
    with open(image, "rb") as f:
        data = bytearray()
        for sector_index in range((min(size, cap) + 2047) // 2048):
            f.seek((lba + sector_index) * 2352)
            raw = f.read(2352)
            if len(raw) != 2352 or raw[:12] != b"\x00" + b"\xff" * 10 + b"\x00":
                raise ValueError("Invalid raw sector sync")
            if raw[15] != 2 or raw[18] & 0x20:
                raise ValueError("Not a MODE2/Form1 data sector")
            data.extend(raw[24:2072])
        return bytes(data[:min(size, cap)])

def pointer_runs(payload, min_count=3):
    """Find adjacent little-endian aligned addresses in 0x80000000..0x801fffff."""
    runs = []
    values = [int.from_bytes(payload[i:i+4], "little")
              for i in range(0, len(payload) - 3, 4)]
    i = 0
    while i < len(values):
        if not 0x80000000 <= values[i] <= 0x801fffff:
            i += 1
            continue
        j = i
        while j < len(values) and 0x80000000 <= values[j] <= 0x801fffff:
            j += 1
        if j - i >= min_count:
            seq = values[i:j]
            runs.append({"offset": i*4, "count": len(seq),
                         "first": f"0x{seq[0]:08x}", "last": f"0x{seq[-1]:08x}",
                         "nondecreasing": all(a<=b for a,b in zip(seq,seq[1:]))})
        i = j
    return runs

def main():
    p=argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("inventory", help="JSON output from inspect_disc.py --json")
    p.add_argument("--prefix", default="/BIN/")
    args=p.parse_args()
    entries=json.loads(open(args.inventory,encoding="utf-8").read())["entries"]
    for e in entries:
        if e["directory"] or not e["path"].startswith(args.prefix):
            continue
        payload=read_payload(args.image,e["lba"],e["size"])
        print(json.dumps({"path":e["path"],"pointer_runs":pointer_runs(payload)}))
if __name__=="__main__":
    main()
