#!/usr/bin/env python3
"""PRIVATE, opt-in color-row contact sheets from owner-supplied CDSTG.BIN.

This is diagnostic source-image visualization, never actual PS1 field output.
The bank/stream ordinal relationship, row choice, BGR555/STP and 4bpp map
pixel order remain HYPOTHESES until a genuine PS1 frame comparison.
Requires Pillow locally, NOT in public CI. Never commit the outputs.
"""
import argparse
import json
from pathlib import Path
import struct

from audit_surf_palette_rows import (
    bgr555_candidate_rgb, read_private_candidates, unpack_candidate_4bpp,
)


def fit_aspect(width, height, max_width, max_height):
    if (any(type(v) is not int or v <= 0 for v in
            (width,height,max_width,max_height))):
        raise ValueError("image and box dimensions must be positive integers")
    scale = min(max_width / width, max_height / height, 1.0)
    return max(1,int(width*scale)), max(1,int(height*scale))


def private_color_sheet(pixels, bank, row, width):
    # Import opt-in dependency at runtime, not in default CI.
    from PIL import Image
    if len(bank) != 512 or type(row) is not int or not 0 <= row < 16:
        raise ValueError("a color candidate requires one 512-byte bank and row 0..15")
    if type(width) is not int or width <= 0:
        raise ValueError("invalid indexed pixel width")
    indices = unpack_candidate_4bpp(pixels)
    if len(indices) % width:
        raise ValueError("hypothetical pixels incompatible with supplied width")
    height = len(indices)//width
    if height < 1:
        raise ValueError("empty candidate texture")
    palette=[]
    for color in struct.unpack_from("<16H", bank, row*32):
        palette.extend(bgr555_candidate_rgb(color))
    image=Image.frombytes("P",(width,height),indices)
    image.putpalette(palette+[0]*(768-len(palette)))
    return image.convert("RGB")


def export_private_palettes(cdstg, output_directory, *, map_index=2):
    from PIL import Image, ImageDraw, ImageFont
    folder=Path(output_directory)
    if not folder.is_dir():
        raise ValueError("private output directory must exist")
    private=read_private_candidates(cdstg,map_index=map_index)
    banks=private["candidate_banks"]
    streams=private["verified_streams"]
    if not banks or len(banks)!=len(streams):
        raise ValueError("candidate bank count differs from verified stream count")
    # Clear, explicit filenames; fail BEFORE writing anything if any file
    # exists to prevent mixing old and new private evidence sets.
    planned=[folder/f"map{map_index:03d}_stream{s['graphics_region_index']:02d}_16_unverified_rows.png"
             for s in streams]
    planned.append(folder/f"map{map_index:03d}_UNVERIFIED_bank_order_row0.png")
    planned.append(folder/"README_PRIVATE_NOT_A_PS1_FRAME.txt")
    if any(p.exists() for p in planned):
        raise FileExistsError("private output already contains a planned filename")
    try:
        font=ImageFont.truetype("DejaVuSans.ttf",14)
        title_font=ImageFont.truetype("DejaVuSans.ttf",18)
    except OSError:
        font=ImageFont.load_default()
        title_font=font
    cards=[]
    for ordinal,(bank,stream) in enumerate(zip(banks,streams)):
        region=stream["graphics_region_index"]
        original=stream["decoded"]
        # 32768 bytes = 256x256 under 4bpp hypothesis.
        # 65536 bytes = 512x256 under 4bpp hypothesis.
        if len(original) not in (32768,65536):
            raise ValueError("a bounded source stream has unsupported 4bpp layout")
        width=256 if len(original)==32768 else 512
        sample=[]
        sheet=Image.new("RGB",(4*272+20,4*257+75),(24,29,36))
        pen=ImageDraw.Draw(sheet)
        pen.text((14,10),
                 f"Map {map_index} region {region}, bank {ordinal}: 16 UNVERIFIED palette choices",
                 font=title_font,fill=(245,247,252))
        pen.text((14,39),
                 "Original bytes; 4bpp, bank order, row choice, STP and position NOT verified",
                 font=font,fill=(255,203,130))
        for row in range(16):
            img=private_color_sheet(original,bank,row,width)
            assert img.size==(width,256)
            dest_w,dest_h=fit_aspect(img.width,img.height,245,216)
            thumb=img.resize((dest_w,dest_h),Image.Resampling.NEAREST)
            col=row%4
            line=row//4
            boxx=12+col*272
            boxy=66+line*257
            x=boxx+(245-dest_w)//2
            y=boxy+(216-dest_h)//2
            sheet.paste(thumb,(x,y))
            pen.text((boxx+6,boxy+218),f"Candidate row {row:02d}",font=font,
                     fill=(226,230,239))
            if row==0:
                sample.append(img)
        sheet.save(planned[ordinal],optimize=True)
        cards.append((region,sample[0]))
    # A contact index does NOT represent tile placement.
    overview=Image.new("RGB",(3*540+24,3*323+74),(24,29,36))
    draw=ImageDraw.Draw(overview)
    draw.text((16,12),
              f"Original Wild Arms map {map_index}: paletted atlas candidates, NOT a scene",
              font=title_font,fill=(245,247,252))
    draw.text((16,42),
              "Row 0 / bank by ordinal = unverified. Image proportions preserved; no alpha.",
              font=font,fill=(255,203,130))
    for number,(region,img) in enumerate(cards):
        bx=12+(number%3)*540
        by=77+(number//3)*323
        draw.rectangle((bx,by,bx+525,by+304),outline=(79,89,108),width=1)
        draw.text((bx+7,by+5),f"Stream #{region} / bank #{number} row 0 HYPOTHESIS",
                  font=font,fill=(235,239,247))
        pw,ph=fit_aspect(*img.size,510,264)
        thumb=img.resize((pw,ph),Image.Resampling.NEAREST)
        overview.paste(thumb,(bx+(525-pw)//2,by+29+(264-ph)//2))
    overview.save(planned[-2],optimize=True)
    planned[-1].write_text(
        "PRIVATE Wild Arms original PS1 asset diagnostics.\n"
        "Generated from user-owned CDSTG.BIN, WITHOUT original runtime CLUT selection.\n"
        "Bank-to-stream and palette row associations are hypotheses only.\n"
        "All index0 and STP/alpha meanings are deliberately uninterpreted.\n"
        "Map graphics are atlases, not a rendered or reconstructed field scene.\n"
        "Thumbnails preserve source width/height proportions; NEVER publish assets to GitHub.\n",
        encoding="utf-8")
    return {"map_index":map_index,"contact_sheet":planned[-2].name,
            "palette_row_variants":16*len(cards),"source_region_count":len(cards),
            "aspect_ratio_preserved":True,"preview_images":[p.name for p in planned[:-2]],
            "provenance":"private original user-provided disc",
            "original_runtime_clut_assignment_verified":False,
            "original_playstation_screen_reconstructed":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdstg",type=Path,help="private source CDSTG.BIN")
    parser.add_argument("private_output_directory",type=Path)
    parser.add_argument("--map-index",type=int,default=2)
    args=parser.parse_args()
    print(json.dumps(export_private_palettes(
        args.cdstg,args.private_output_directory,map_index=args.map_index),
        indent=2,sort_keys=True))


if __name__=="__main__":
    main()
