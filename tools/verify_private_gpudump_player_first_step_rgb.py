#!/usr/bin/env python3
"""OWNER-PRIVATE GPUDump Player *first Step* post-VSync visual witness.

After Rewind, upstream GPUDumpPlayer::step() executes native typed GPU
records until the first VSync; player->frame() becomes 1. Its detached
software GPU exposes current VRAM internally, but the stock GUI does
NOT document a lossless post-step VRAM export. Therefore the post-step
VRAM and matching PNG are explicitly **operator supplied**, and their
origin/timing remain UNATTESTED even if every checked RGB byte matches.

This gate binds the original native GPUDUMP to Stage451's imported
pretrace VRAM/GP0/VSync, compares independently supplied post-step
1MiB u16le VRAM and exact unscaled PNG ROI, and distinguishes changes
from rewind. It does NOT emulate GP0 drawing or certify Surf Village.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from bind_private_pcsx_first_frame_evidence import bind_private_first_frame_capture
from decode_private_opaque_rgb_png import decode_private_opaque_rgb_png
from import_private_pcsx_native_gpudump import MAX_DUMP_BYTES,read_native_gpu_dump
from verify_private_gpudump_player_rewind_rgb import (
    VRAM_BYTES, VRAM_WIDTH, compare_private_rewind_vram_rgb,
    private_pretrace_display_rectangle,
)

MAX_PNG_BYTES=16*1024*1024
EXPECTED_SHA=re.compile(r"[0-9a-f]{64}")


def first_step_change_summary(before, after, *, x,y,width,height):
    """Compare original VRAM halfwords; never serialize raw u16 values."""
    if (type(before) is not bytes or type(after) is not bytes or
            len(before)!=VRAM_BYTES or len(after)!=VRAM_BYTES or
            any(type(n) is not int for n in (x,y,width,height)) or
            not 0<=x<VRAM_WIDTH or not 0<=y<512 or
            width<1 or height<1 or x+width>VRAM_WIDTH or y+height>512):
        raise ValueError("invalid paired VRAM states or first-step ROI")
    # Distinguish the full u16 VRAM state from the visible 15-bit RGB
    # that the pinned PCSX Player GUI actually expands on screen.
    changed_words=0
    for offset in range(0,VRAM_BYTES,2):
        if before[offset:offset+2]!=after[offset:offset+2]:
            changed_words+=1
    changed_roi_words=0
    changed_roi_visible=0
    for iy in range(height):
        for ix in range(width):
            addr=((y+iy)*VRAM_WIDTH+x+ix)*2
            a=before[addr]|before[addr+1]<<8
            b=after[addr]|after[addr+1]<<8
            if a!=b:
                changed_roi_words+=1
            if (a&0x7fff)!=(b&0x7fff):
                changed_roi_visible+=1
    return {
        "whole_vram_changed_u16_halfword_count":changed_words,
        "roi_changed_u16_halfword_count":changed_roi_words,
        "roi_visibly_changed_rgb555_pixel_count":changed_roi_visible,
        "poststep_vram_identical_to_initial_pretrace":
            changed_words==0,
        "roi_rgb_unchanged_since_rewind":
            changed_roi_visible==0,
        "bit15_only_changes_do_not_imply_visible_rgb_difference":True,
    }


def verify_private_gpudump_player_first_step(
        native_gpudump, initial_vram, trace_jsonl,
        poststep_vram, poststep_png, *, x,y,width,height,
        expected_native_sha256=None, expected_poststep_vram_sha256=None,
        expected_poststep_png_sha256=None, expected_frame=None,
        expected_player_frame_label=None,
        require_exact_rgb=True, require_native_display_window=False,
        require_changed_roi=False):
    """Check first-Step image-to-VRAM equality; never claim VRAM origin proof."""
    for key,value in (
            ("require_exact_rgb",require_exact_rgb),
            ("require_native_display_window",require_native_display_window),
            ("require_changed_roi",require_changed_roi)):
        if type(value) is not bool:
            raise ValueError(key+" must be a boolean")
    if (expected_player_frame_label is not None and
            (type(expected_player_frame_label) is not int or
             expected_player_frame_label!=1)):
        raise ValueError("expected first player Step must show frame label 1")
    for key,value in (
            ("expected_poststep_vram_sha256",expected_poststep_vram_sha256),
            ("expected_poststep_png_sha256",expected_poststep_png_sha256)):
        if value is not None and (
                type(value) is not str or EXPECTED_SHA.fullmatch(value) is None):
            raise ValueError(key+" must be lowercase SHA-256")

    src,pre,gp0,after,screen=map(
        Path,(native_gpudump,initial_vram,trace_jsonl,
              poststep_vram,poststep_png))
    paths=(src,pre,gp0,after,screen)
    if (len(set(str(path) for path in paths))!=5 or
            any(path.is_symlink() or not path.is_file() for path in paths) or
            not 20<=src.stat().st_size<=MAX_DUMP_BYTES or
            pre.stat().st_size!=VRAM_BYTES or
            after.stat().st_size!=VRAM_BYTES or
            not 0<screen.stat().st_size<=MAX_PNG_BYTES):
        raise ValueError("invalid or aliased owner-private first-Step evidence")

    # Check that the native file and the initial VRAM/GP0 data really
    # belong together and the first recorded frame ends at a valid VSync.
    binding=bind_private_first_frame_capture(
        src,pre,gp0,expected_native_sha256=expected_native_sha256,
        expected_frame=expected_frame)
    source_bytes=src.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest()!=binding["native_dump_sha256"]:
        raise ValueError("native GPUDUMP changed after first-frame integrity audit")
    initial_bytes=pre.read_bytes()
    if hashlib.sha256(initial_bytes).hexdigest()!=binding[
            "imported_prepacket_vram_sha256"]:
        raise ValueError("original initial VRAM changed after binding")

    if require_native_display_window:
        display=private_pretrace_display_rectangle(
            read_native_gpu_dump(source_bytes))
        if (x,y,width,height)!=display:
            raise ValueError("post-Step PNG ROI differs from native GP1 display window")
        # Stage447 rejects live GP1 before first VSync. Consequently
        # the original pretrace display geometry remains unchanged
        # through this *supported subset* of the first Step.
    after_bytes=after.read_bytes()
    if len(after_bytes)!=VRAM_BYTES:
        raise ValueError("post-Step VRAM changed size during read")
    after_digest=hashlib.sha256(after_bytes).hexdigest()
    if (expected_poststep_vram_sha256 is not None and
            after_digest!=expected_poststep_vram_sha256):
        raise ValueError("post-Step VRAM differs from independent expected SHA-256")

    png_bytes=screen.read_bytes()
    if not 0<len(png_bytes)<=MAX_PNG_BYTES:
        raise ValueError("post-Step PNG changed size during read")
    png_sha=hashlib.sha256(png_bytes).hexdigest()
    if (expected_poststep_png_sha256 is not None and
            png_sha!=expected_poststep_png_sha256):
        raise ValueError("post-Step PNG differs from independent expected SHA-256")
    dimensions, rgb=decode_private_opaque_rgb_png(png_bytes)
    if any(type(q) is not int for q in (x,y,width,height)) or (
            width,height)!=dimensions:
        raise ValueError("post-Step PNG must be an unscaled exact ROI")
    compared=compare_private_rewind_vram_rgb(
        after_bytes,rgb,x,y,width,height)
    delta=first_step_change_summary(
        initial_bytes,after_bytes,x=x,y=y,width=width,height=height)
    if require_changed_roi and not delta[
            "roi_visibly_changed_rgb555_pixel_count"]:
        raise ValueError("first Step ROI shows no visible RGB555 change from Rewind")
    if require_exact_rgb and not compared["rgb_pixel_values_exactly_equal"]:
        raise ValueError("post-Step owner PNG RGB differs from supplied post-Step VRAM")

    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PCSX_GPUDUMP_PLAYER_FIRST_STEP_VISUAL_WITNESS",
        "status":(
            "POST_STEP_ONE_RGB_EQUALITY_UNATTESTED_PLAYER_SNAPSHOT"
            if compared["rgb_pixel_values_exactly_equal"] else
            "POST_STEP_ONE_RGB_MISMATCH_NO_VISUAL_BINDING"),
        "native_gpudump_sha256":binding["native_dump_sha256"],
        "pretrace_vram_sha256":binding["imported_prepacket_vram_sha256"],
        "first_frame_gp0_jsonl_sha256":binding["imported_gp0_jsonl_sha256"],
        "native_first_step_vsync_gpu_cycle":
            binding["native_first_frame_ended_at_gpu_cycle"],
        "expected_player_frame_label":1,
        "player_frame_label_operator_confirmed":
            expected_player_frame_label is not None,
        "poststep_vram_sha256":after_digest,
        "poststep_png_sha256":png_sha,
        "native_gp1_display_window_checked":
            require_native_display_window,
        "independent_poststep_vram_digest_compared":
            expected_poststep_vram_sha256 is not None,
        "independent_poststep_png_digest_compared":
            expected_poststep_png_sha256 is not None,
        "roi_rgb_exactly_equal":compared["rgb_pixel_values_exactly_equal"],
        "roi_pixel_count":compared["compared_rgb_pixel_count"],
        "roi_mismatched_rgb_pixel_count":compared["mismatched_rgb_pixel_count"],
        "roi_maximum_rgb_error":compared["maximum_absolute_rgb_channel_error"],
        "roi_mean_absolute_rgb_error":compared["mean_absolute_rgb_channel_error"],
        "roi_expected_rgb_sha256":compared["pretrace_vram_visible_rgb_sha256"],
        "roi_observed_rgb_sha256":compared["observed_png_rgb_sha256"],
        "change_since_initial_rewind":delta,
        "interpretation":{
            "native_first_step_executes_until_first_vsync":True,
            "poststep_vram_origin_from_player_is_not_authenticated":True,
            "poststep_png_origin_from_player_is_not_authenticated":True,
            "frame_label_is_operator_assertion_not_cryptographic_identity":True,
            "pixel_match_does_not_prove_gpu_command_replay_result":True,
            "poststep_image_not_independently_rendered_by_this_tool":True,
            "initial_and_poststep_vram_are_distinct_evidence_surfaces":True,
            "genuine_original_wild_arms_scene_and_disc_unverified":True,
            "raw_gpu_words_vram_png_and_original_palette_colors_not_exported":True,
            "all_hashes_and_reports_must_remain_owner_private":True,
        },
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_gpudump")
    parser.add_argument("private_initial_vram_u16le")
    parser.add_argument("private_first_frame_gp0_jsonl")
    parser.add_argument("private_player_poststep_vram_u16le")
    parser.add_argument("private_player_poststep_unscaled_png")
    for name in ("x","y","width","height"):
        parser.add_argument("--"+name,type=int,required=True)
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-poststep-vram-sha256")
    parser.add_argument("--expected-poststep-png-sha256")
    parser.add_argument("--expected-frame",type=int)
    parser.add_argument("--expected-player-frame-label",type=int)
    parser.add_argument("--require-native-display-window",action="store_true")
    parser.add_argument("--require-changed-roi",action="store_true")
    parser.add_argument("--allow-rgb-mismatch",action="store_true")
    args=parser.parse_args()
    report=verify_private_gpudump_player_first_step(
        args.private_native_gpudump,args.private_initial_vram_u16le,
        args.private_first_frame_gp0_jsonl,
        args.private_player_poststep_vram_u16le,
        args.private_player_poststep_unscaled_png,
        x=args.x,y=args.y,width=args.width,height=args.height,
        expected_native_sha256=args.expected_native_sha256,
        expected_poststep_vram_sha256=args.expected_poststep_vram_sha256,
        expected_poststep_png_sha256=args.expected_poststep_png_sha256,
        expected_frame=args.expected_frame,
        expected_player_frame_label=args.expected_player_frame_label,
        require_native_display_window=args.require_native_display_window,
        require_changed_roi=args.require_changed_roi,
        require_exact_rgb=not args.allow_rgb_mismatch)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
