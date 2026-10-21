#!/usr/bin/env python3
"""Private-only export of two verified Wild Arms PS1 256x256 icon textures.

Reference: Christian Bauer's wa1tools v1.2 'untrans' icon targets:
https://github.com/cebix/wa1tools (ISC license).
The user must supply their legally obtained CDFLR.BIN; no assets bundled.
Do not commit the resulting PNGs or private source file to public GitHub.
"""
import argparse
import struct
from pathlib import Path

from wa1_lzss import decode_wa1_lzss

SLOT_BYTES=0x3A000
TARGETS=(
    (48,0x120,"battle_icons.png"),
    (56,0x60,"battle_icons2.png"),
)


def unpack_indices_4bpp(raw):
    output=bytearray(len(raw)*2)
    for i,value in enumerate(raw):
        output[2*i]=value&15
        output[2*i+1]=value>>4
    return bytes(output)


def ps1_clut_rgb(brush):
    if len(brush)!=32:
        raise ValueError("expected 16 PS1 BGR555 colors")
    rgb=[]
    for i in range(16):
        color=struct.unpack_from("<H",brush,i*2)[0]
        # wa1tools uses magenta as its *export placeholder* for raw zero.
        # Genuine runtime blending/transparency requires further study.
        if color==0:
            rgb.extend((255,0,255))
        else:
            rgb.extend((
                (color&31)*255//31,
                ((color>>5)&31)*255//31,
                ((color>>10)&31)*255//31,
            ))
    return rgb


def extract_icons(private_cdflr, private_output_dir):
    # Pillow is needed only for the optional local PNG export, not CI.
    from PIL import Image
    private_cdflr=Path(private_cdflr)
    private_output_dir=Path(private_output_dir)
    if not private_output_dir.is_dir():
        raise ValueError("output directory must already exist")
    with private_cdflr.open("rb") as source:
        block=source.read(SLOT_BYTES)
    if len(block)!=SLOT_BYTES:
        raise ValueError("CDFLR first slot truncated")
    pointers=struct.unpack_from("<58I",block)
    base=pointers[0]-256
    offsets=[word-base for word in pointers]
    if (offsets[0]!=256 or offsets[-1]+4>SLOT_BYTES or
            any(a>=b for a,b in zip(offsets,offsets[1:]))):
        raise ValueError("CDFLR first slot pointer table invalid")
    results=[]
    for palette_index,palette_offset,name in TARGETS:
        data_index=palette_index+1
        palette_start=offsets[palette_index]
        palette_end=offsets[palette_index+1]
        if palette_start+palette_offset+32>palette_end:
            raise ValueError("CLUT slice exceeds pointer-bounded region")
        clut=block[palette_start+palette_offset:palette_start+palette_offset+32]
        stream_start=offsets[data_index]
        stream_end=offsets[data_index+1] if data_index<57 else SLOT_BYTES
        stream=block[stream_start:stream_end]
        pixels,used=decode_wa1_lzss(stream,max_output=0x8000)
        if len(pixels)!=0x8000 or used>len(stream):
            raise ValueError("icon stream is not bounded")
        if data_index<57 and len(stream)-used>3:
            raise ValueError("compressed icon stream crosses expected boundary")
        indices=unpack_indices_4bpp(pixels)
        if len(indices)!=256*256:
            raise ValueError("decoded icons have invalid pixel count")
        out=private_output_dir/name
        if out.exists():
            raise FileExistsError(f"refusing to overwrite {out}")
        image=Image.frombytes("P",(256,256),indices)
        palette=ps1_clut_rgb(clut)
        image.putpalette(palette+[0]*(768-len(palette)))
        image.save(out)
        results.append({"name":name,"dimensions":[256,256],
                        "decoded_bytes":len(pixels),
                        "compressed_used_bytes":used,
                        "trailing_bytes_in_pointer_bound":len(stream)-used})
    return results


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cdflr",type=Path,help="user-owned CDFLR.BIN")
    ap.add_argument("private_output_dir",type=Path,help="existing PRIVATE destination")
    args=ap.parse_args()
    for item in extract_icons(args.private_cdflr,args.private_output_dir):
        print(item)


if __name__=="__main__":
    main()
