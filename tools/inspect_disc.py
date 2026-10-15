#!/usr/bin/env python3
"""Read-only ISO9660 inventory for raw 2352-byte PS1 MODE2/Form1 images."""
import argparse
import json

def inspect(path):
    with open(path, "rb") as f:
        def sector(lba):
            f.seek(lba * 2352)
            raw = f.read(2352)
            if len(raw) != 2352 or raw[:12] != b"\x00" + b"\xff" * 10 + b"\x00":
                raise ValueError(f"Invalid sector {lba}")
            if raw[15] != 2 or raw[18] & 0x20:
                raise ValueError(f"Not MODE2/Form1 at {lba}")
            return raw[24:2072]
        def record(buf):
            n = buf[32]
            return {"name": buf[33:33+n].decode("ascii", "replace"),
                    "lba": int.from_bytes(buf[2:6], "little"),
                    "size": int.from_bytes(buf[10:14], "little"),
                    "directory": bool(buf[25] & 2)}
        def extent(lba, size):
            return b"".join(sector(lba+i) for i in range((size+2047)//2048))[:size]
        pvd = sector(16)
        if pvd[0] != 1 or pvd[1:6] != b"CD001":
            raise ValueError("ISO9660 PVD not found")
        root = record(pvd[156:156+pvd[156]])
        entries, visited = [], set()
        def walk(directory, prefix="", depth=0):
            if depth > 20 or (directory["lba"], directory["size"]) in visited:
                return
            visited.add((directory["lba"], directory["size"]))
            blob = extent(directory["lba"], directory["size"])
            pos = 0
            while pos < len(blob):
                n = blob[pos]
                if not n:
                    pos = (pos//2048+1)*2048
                    continue
                entry = record(blob[pos:pos+n])
                pos += n
                if entry["name"] in ("\x00", "\x01"):
                    continue
                entry["path"] = prefix + "/" + entry.pop("name")
                entries.append(entry)
                if entry["directory"]:
                    walk(entry, entry["path"], depth+1)
        walk(root)
        return {"volume": pvd[40:72].decode("ascii", "replace").strip(), "entries": entries}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = inspect(args.bin)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Volume:", result["volume"])
        for item in result["entries"]:
            print(item["path"], item["size"], item["lba"], "DIR" if item["directory"] else "FILE")
