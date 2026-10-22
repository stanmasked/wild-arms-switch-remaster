#!/usr/bin/env python3
"""OWNER-PRIVATE pixel check of PCSX-Redux GPUDump Player's REWIND view.

The pinned upstream GUI constructs its rewind image from full 1024x512
u16le VRAM, expands 5-bit PS1 R/G/B to 8-bit by shifting left 3,
ignores bit15 in the visible RGB output, and optionally crops using
pretrace GP1(05)/GP1(08) display settings.

Check an owner-supplied unscaled, unfiltered PNG ROI against those exact
pretrace VRAM bytes FROM THE SAME native GPUDUMP independently bound via
Stage451. This is NOT a post-GP0 first-frame render and does NOT prove
the PNG was actually extracted from the native Dump Player UI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from audit_private_surf_reference_patch import _opaque_rgb_png
from bind_private_pcsx_first_frame_evidence import bind_private_first_frame_capture
from import_private_pcsx_native_gpudump import (
    GP1, TRACE_BEGIN, MAX_DUMP_BYTES, read_native_gpu_dump
)

VRAM_WIDTH = 1024
VRAM_HEIGHT = 512
VRAM_BYTES = VRAM_WIDTH * VRAM_HEIGHT * 2
MAX_PIXEL_COUNT = 1024 * 512
HEX_SHA = re.compile(r"[0-9a-f]{64}")


def private_pretrace_display_rectangle(records):
    """Derive rewind display-only crop from the actual GP1 preamble.

    Matches pinned upstream src/gui/widgets/gpudump.cc. Reject duplicates
    or unavailable initial GP1 controls instead of guessing defaults.
    """
    seen={}
    found_begin=False
    for kind,words in records:
        if kind==TRACE_BEGIN:
            found_begin=True
            break
        if kind!=GP1:
            continue
        for word in words:
            if type(word) is not int or not 0<=word<=0xffffffff:
                raise ValueError("invalid GP1 restore word")
            cmd=word>>24
            if cmd in (5,8):
                if cmd in seen:
                    raise ValueError("duplicate native GP1 display restore control")
                seen[cmd]=word
    if not found_begin or set(seen)!={5,8}:
        raise ValueError("native GP1 display start/mode not proven in pretrace")
    start,mode=seen[5]&0xffffff,seen[8]&0xffffff
    x=start&0x3ff
    y=(start>>10)&0x1ff
    widths=(256,320,512,640)
    width=368 if mode&0x40 else widths[mode&3]
    height=480 if mode&0x24==0x24 else 240
    if x+width>VRAM_WIDTH or y+height>VRAM_HEIGHT:
        raise ValueError("native GP1 rewind display window wraps outside VRAM")
    return (x,y,width,height)


def compare_private_rewind_vram_rgb(
        vram, image_rgb, x, y, width, height):
    """Compare exact 5->8-bit visual RGB; never export raw pixel values."""
    if (type(vram) not in (bytes,bytearray)
            or len(vram)!=VRAM_BYTES or
            type(image_rgb) is not bytes or
            any(type(n) is not int for n in (x,y,width,height))
            or x<0 or y<0 or width<1 or height<1
            or x+width>VRAM_WIDTH or y+height>VRAM_HEIGHT
            or width*height>MAX_PIXEL_COUNT or
            len(image_rgb)!=width*height*3):
        raise ValueError("invalid rewind VRAM/PNG ROI dimensions")
    generated=bytearray(width*height*3)
    diff_pixels=0
    total_abs=0
    maximum=0
    for j in range(height):
        row_word=(y+j)*VRAM_WIDTH+x
        for i in range(width):
            vram_offset=2*(row_word+i)
            raw=vram[vram_offset]|(vram[vram_offset+1]<<8)
            off=(j*width+i)*3
            # Same R/G/B packing and <<3 expansion as pinned
            # PCSX-Redux GPU Dump Player updateTexture().
            for channel,val in enumerate((
                    (raw&31)<<3,((raw>>5)&31)<<3,((raw>>10)&31)<<3)):
                generated[off+channel]=val
            per_pixel_max=0
            for channel in range(3):
                gap=abs(generated[off+channel]-image_rgb[off+channel])
                total_abs+=gap
                per_pixel_max=max(per_pixel_max,gap)
            if per_pixel_max:
                diff_pixels+=1
            maximum=max(maximum,per_pixel_max)
    return {
        "roi_x":x,"roi_y":y,"roi_width":width,"roi_height":height,
        "compared_rgb_pixel_count":width*height,
        "mismatched_rgb_pixel_count":diff_pixels,
        "matching_rgb_pixel_count":width*height-diff_pixels,
        "rgb_pixel_values_exactly_equal":diff_pixels==0,
        "maximum_absolute_rgb_channel_error":maximum,
        "mean_absolute_rgb_channel_error":round(
            total_abs/(3*width*height),8),
        "pretrace_vram_visible_rgb_sha256":hashlib.sha256(generated).hexdigest(),
        "observed_png_rgb_sha256":hashlib.sha256(image_rgb).hexdigest(),
        "bit15_mask_is_not_transparency_for_display":True,
        "five_bit_rgb_expanded_by_left_shift_three_not_gamma_adjustment":True,
    }


def verify_private_gpudump_rewind_image(
        native_path,initial_vram_path,trace_path,owner_png_path,
        *,x,y,width,height,require_exact_rgb=True,
        require_native_display_window=False,
        expected_png_sha256=None,expected_native_sha256=None,
        expected_frame=None):
    """Conditionally verify PNG pixels match original NATIVE PRETRACE VRAM."""
    if (type(require_exact_rgb) is not bool
            or type(require_native_display_window) is not bool
            or (expected_png_sha256 is not None and
                (type(expected_png_sha256) is not str or
                 HEX_SHA.fullmatch(expected_png_sha256) is None))):
        raise ValueError("invalid rewind PNG strictness or expected digest")
    native_path=Path(native_path)
    pre=Path(initial_vram_path)
    png=Path(owner_png_path)
    if (native_path.is_symlink() or not native_path.is_file()
            or not 20<=native_path.stat().st_size<=MAX_DUMP_BYTES
            or pre.is_symlink() or not pre.is_file()
            or pre.stat().st_size!=VRAM_BYTES
            or png.is_symlink() or not png.is_file()
            or not 0<png.stat().st_size<=16*1024*1024
            or len({str(native_path),str(pre),str(png),str(Path(trace_path))})!=4):
        raise ValueError("invalid or aliased private rewind inputs")
    binding=bind_private_first_frame_capture(
        native_path,pre,trace_path,expected_native_sha256=expected_native_sha256,
        expected_frame=expected_frame)
    native_bytes=native_path.read_bytes()
    if hashlib.sha256(native_bytes).hexdigest()!=binding["native_dump_sha256"]:
        raise ValueError("native GPU dump changed after Stage451 binding")
    if require_native_display_window:
        display=private_pretrace_display_rectangle(
            read_native_gpu_dump(native_bytes))
        if any(type(n) is not int for n in (x,y,width,height)) or (
                x,y,width,height)!=display:
            raise ValueError("provided PNG ROI does not equal native GP1 display window")
    image=png.read_bytes()
    if not image or len(image)>16*1024*1024:
        raise ValueError("private rewind PNG changed size during read")
    image_sha=hashlib.sha256(image).hexdigest()
    if expected_png_sha256 is not None and image_sha!=expected_png_sha256:
        raise ValueError("owner PNG differs from independent expected hash")
    image_dimensions,decoded=_opaque_rgb_png(image)
    if image_dimensions!=(width,height):
        raise ValueError("rewind PNG must have exact unscaled ROI dimensions")
    vram=pre.read_bytes()
    if hashlib.sha256(vram).hexdigest()!=binding["imported_prepacket_vram_sha256"]:
        raise ValueError("pretrace VRAM changed after Stage451 integrity binding")
    result=compare_private_rewind_vram_rgb(
        vram,decoded.tobytes(),x,y,width,height)
    if require_exact_rgb and not result["rgb_pixel_values_exactly_equal"]:
        raise ValueError("owner rewind PNG RGB differs from native pretrace VRAM")
    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PCSX_GPUDUMP_PLAYER_REWIND_VISUAL_STATE",
        "status":(
            "REWIND_PRETRACE_RGB_EQUALITY_WITH_UNVERIFIED_PNG_PROVENANCE"
            if result["rgb_pixel_values_exactly_equal"] else
            "REWIND_PNG_RGB_MISMATCH_NO_VISUAL_BINDING"),
        "native_gpudump_sha256":binding["native_dump_sha256"],
        "pretrace_vram_sha256":binding["imported_prepacket_vram_sha256"],
        "first_frame_gp0_jsonl_sha256":binding["imported_gp0_jsonl_sha256"],
        "native_first_completed_vsync_cycle_stamp":
            binding["native_first_frame_ended_at_gpu_cycle"],
        "owner_rewind_png_sha256":image_sha,
        "native_gp1_display_window_explicitly_verified":
            require_native_display_window,
        "compared_rewind_region":result,
        "interpretation":{
            "snapshot_is_at_player_rewind_before_first_live_gp0":True,
            "png_actual_origin_from_player_ui_not_attested":True,
            "matching_rgb_not_proof_of_same_original_gameplay_frame":True,
            "not_rendered_frame_after_first_native_vsync":True,
            "native_gp0_first_frame_only_covered_by_stage451_integrity":True,
            "actual_gpu_polygon_rasterization_clut_caches_unverified":True,
            "no_original_png_pixels_gp0_vram_or_palette_words_exported":True,
            "all_sha256_and_visual_metadata_must_remain_owner_private":True,
        },
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_gpudump")
    parser.add_argument("private_initial_vram_u16le")
    parser.add_argument("private_first_frame_gp0_jsonl")
    parser.add_argument("private_rewind_unscaled_roi_png")
    for arg in ("x","y","width","height"):
        parser.add_argument("--"+arg,type=int,required=True)
    parser.add_argument("--allow-rgb-mismatch",action="store_true")
    parser.add_argument("--require-native-display-window",action="store_true")
    parser.add_argument("--expected-png-sha256")
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-frame",type=int)
    args=parser.parse_args()
    report=verify_private_gpudump_rewind_image(
        args.private_native_gpudump,args.private_initial_vram_u16le,
        args.private_first_frame_gp0_jsonl,args.private_rewind_unscaled_roi_png,
        x=args.x,y=args.y,width=args.width,height=args.height,
        require_exact_rgb=not args.allow_rgb_mismatch,
        require_native_display_window=args.require_native_display_window,
        expected_png_sha256=args.expected_png_sha256,
        expected_native_sha256=args.expected_native_sha256,
        expected_frame=args.expected_frame)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
