#!/usr/bin/env python3
"""Static MIPS signature verification for Wild Arms (USA) indexed 88-byte records.

Reads user-owned raw MODE2/Form1 disc. Does not export copyrighted executable bytes.
"""
import argparse
import json
from pathlib import Path

ENTRY = 0x80078DB0
CALLEE = 0x8006CE70
# Arithmetic sequence: 2*a0; +a0 => 3; <<2 => 12; -a0 => 11; <<3 => 88.
STRIDE_OPS = (0x00041040, 0x00441021, 0x00021080, 0x00441023,
              0x000210C0)
GLOBAL_OPS = (0x3C10800D, 0x8E102C44)
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"

def compute_stride(index):
    v = ((index << 1) + index)
    v = ((v << 2) - index)
    return v << 3

def verify_words(words):
    if len(words) < 47:
        raise ValueError("truncated function signature")
    if tuple(words[3:7]) != STRIDE_OPS[:4] or words[10] != STRIDE_OPS[4]:
        raise ValueError("stride instruction signature mismatch")
    if (words[8], words[9]) != GLOBAL_OPS:
        raise ValueError("global pointer signature mismatch")
    if words[16] != 0x26040004:
        raise ValueError("expected addiu a0,s0,4")
    if words[17] != 0xA2020000 or words[19] != 0xA2060001:
        raise ValueError("record header stores differ")
    if words[18] != (0x0c000000 | ((CALLEE >> 2) & 0x03ffffff)):
        raise ValueError("initializer JAL signature differs")
    # JAL delay slot at index 19 saves input byte a2 into record byte 1.
    expected_stores = {25: 0xA6020052, 26: 0xA6120002,
                       27: 0xA6030050, 39: 0xAE030054}
    for index, expected in expected_stores.items():
        if words[index] != expected:
            raise ValueError(f"record field store differs at index {index}")
    return {"entry": f"0x{ENTRY:08X}", "record_stride_bytes": compute_stride(1),
            "base_pointer_variable": "0x800D2C44",
            "initializer": f"0x{CALLEE:08X}",
            "initializer_argument_offset": 4,
            "initializer_argument_register": "a0",
            "record_header_byte_offsets": [0, 1],
            "additional_direct_record_store_offsets": [0x02, 0x50, 0x52, 0x54],
            "note": "stride is verified, allocation boundaries and role unknown"}

def read_exe(image, record):
    contents = bytearray()
    with open(image, "rb") as f:
        for i in range((record["size"] + 2047) // 2048):
            f.seek((record["lba"] + i) * 2352)
            s = f.read(2352)
            if len(s) != 2352 or s[:12] != SYNC or s[15] != 2:
                raise ValueError("bad raw disc sector")
            if s[18] & 0x20 or s[16:20] != s[20:24]:
                raise ValueError("not MODE2/Form1")
            contents.extend(s[24:2072])
    exe = bytes(contents[:record["size"]])
    if len(exe) < 2048 or exe[:8] != b"PS-X EXE":
        raise ValueError("invalid PS-X EXE header")
    load = int.from_bytes(exe[0x18:0x1c], "little")
    size = int.from_bytes(exe[0x1c:0x20], "little")
    off = 2048 + ENTRY - load
    if off < 2048 or off + 47*4 > min(len(exe), 2048+size):
        raise ValueError("target outside EXE")
    return [int.from_bytes(exe[off+4*i:off+4*i+4], "little") for i in range(47)]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("disc")
    parser.add_argument("inventory", help="inspect_disc.py --json")
    args = parser.parse_args()
    records = json.loads(Path(args.inventory).read_text(encoding="utf8"))["entries"]
    candidates = [r for r in records if r["path"] == "/EXE/WILDARMS.EXE;1"]
    if len(candidates) != 1:
        parser.error("WILDARMS.EXE not found")
    print(json.dumps(verify_words(read_exe(args.disc, candidates[0])), indent=2))

if __name__ == "__main__":
    main()
