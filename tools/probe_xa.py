#!/usr/bin/env python3
"""Read-only probe of PS1 CD-ROM XA sector metadata; no asset extraction."""
import argparse, collections, json
from pathlib import Path

def probe(image, inventory, max_sectors=128):
    entries=json.loads(Path(inventory).read_text())["entries"]
    output=[]
    with open(image,"rb") as disc:
        for entry in entries:
            if entry["directory"]: continue
            counts=collections.Counter()
            samples=[]
            for i in range(min(max_sectors,(entry["size"]+2047)//2048)):
                disc.seek((entry["lba"]+i)*2352)
                s=disc.read(2352)
                if len(s)!=2352 or s[:12]!=b"\x00"+b"\xff"*10+b"\x00":
                    raise ValueError(f"Bad sync: {entry['path']} sector {i}")
                mode=s[15]
                sub=s[16:20]
                if mode==2 and s[16:20]!=s[20:24]:
                    raise ValueError(f"XA subheader mismatch: {entry['path']} sector {i}")
                counts[(mode,sub[0],sub[1],sub[2])]+=1
                if i==0: samples=list(s[24:40])
            output.append({"path":entry["path"],"sampled_sectors":sum(counts.values()),
                "sector_types":[{"mode":k[0],"file":k[1],"submode":k[2],"coding":k[3],"count":v}
                                for k,v in sorted(counts.items())],
                "first_payload_hex":bytes(samples).hex()})
    return output

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("image");p.add_argument("inventory")
    p.add_argument("--max-sectors",type=int,default=128)
    args=p.parse_args()
    print(json.dumps(probe(args.image,args.inventory,args.max_sectors),indent=2))
