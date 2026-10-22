#!/usr/bin/env python3
"""Verify a frozen GPUDump Player Frame 1 VRAM export from owner-local patch.

Single-file exclusive-create binary format (32 byte header + 1 MiB):
  offset  0: ASCII WA1STEPVRAMv1 + 3 NULs
  offset 16: little-endian uint64 Player frame == 1
  offset 24: little-endian uint32 VRAM byte length == 1048576
  offset 28: little-endian uint32 CRC32 of the following VRAM
  offset 32: raw u16le 1024 x 512 PS1 VRAM

The patched PCSX-Redux GUI writes this from DETACHED Player GPU at
button-click time. The file is self-consistent but does NOT contain a
hash of the native GPU dump: which dump the operator loaded is STILL
not cryptographically attested. No games/captures live in public CI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from bind_private_pcsx_first_frame_evidence import bind_private_first_frame_capture
from decode_private_opaque_rgb_png import decode_private_opaque_rgb_png
from verify_private_gpudump_player_rewind_rgb import (
    VRAM_BYTES, compare_private_rewind_vram_rgb,
)
from verify_private_gpudump_player_first_step_rgb import first_step_change_summary

MAGIC=b"WA1STEPVRAMv1\x00\x00\x00"
HEADER=struct.Struct("<16sQII")
MAX_PNG_BYTES=16*1024*1024
SHA256=re.compile("[0-9a-f]{64}")


def parse_private_detached_step1_snapshot(binary):
    if type(binary) is not bytes or len(binary)!=HEADER.size+VRAM_BYTES:
        raise ValueError("Step 1 player export must contain exactly 32 + 1048576 bytes")
    magic,frame,length,checksum=HEADER.unpack_from(binary)
    if magic!=MAGIC:
        raise ValueError("unknown or corrupt detached Player export magic")
    if frame!=1:
        raise ValueError("detached GPU export is not from Player Frame 1")
    if length!=VRAM_BYTES:
        raise ValueError("invalid declared detached Player VRAM length")
    raw=binary[HEADER.size:]
    actual=zlib.crc32(raw)&0xffffffff
    if checksum!=actual:
        raise ValueError("detached Player VRAM CRC32 mismatch")
    return {"frame":frame,"vram_sha256":hashlib.sha256(raw).hexdigest(),
            "raw":raw,"crc32_verified":True}


def verify_private_detached_step1_export(
        native_path, initial_path, gp0_trace_path,
        exported_snapshot_path, player_png_path, *,
        x,y,width,height, expected_snapshot_sha256=None,
        expected_png_sha256=None, expected_native_sha256=None,
        expected_frame=None, require_changed_roi=False,
        require_exact_rgb=True):
    if type(require_changed_roi) is not bool or type(require_exact_rgb) is not bool:
        raise ValueError("strict replay comparison options must be booleans")
    for name,value in (
            ("snapshot",expected_snapshot_sha256),
            ("PNG",expected_png_sha256)):
        if value is not None and (
                type(value) is not str or SHA256.fullmatch(value) is None):
            raise ValueError(name+" SHA-256 expectation must be lowercase 64 hex")
    source,initial,trace,snapshot,png=map(
        Path,(native_path,initial_path,gp0_trace_path,
              exported_snapshot_path,player_png_path))
    paths=(source,initial,trace,snapshot,png)
    if (len(set(map(str,paths)))!=5 or
            any(p.is_symlink() or not p.is_file() for p in paths) or
            snapshot.stat().st_size!=HEADER.size+VRAM_BYTES or
            not 0<png.stat().st_size<=MAX_PNG_BYTES):
        raise ValueError("invalid or aliased private Player export inputs")
    binding=bind_private_first_frame_capture(
        source,initial,trace,
        expected_native_sha256=expected_native_sha256,
        expected_frame=expected_frame)
    current=source.read_bytes()
    if hashlib.sha256(current).hexdigest()!=binding["native_dump_sha256"]:
        raise ValueError("native GPU dump changed after first-frame binding")
    before=initial.read_bytes()
    if hashlib.sha256(before).hexdigest()!=binding["imported_prepacket_vram_sha256"]:
        raise ValueError("initial VRAM changed after native binding")

    binary=snapshot.read_bytes()
    if len(binary)!=HEADER.size+VRAM_BYTES:
        raise ValueError("detached Player export changed length during read")
    snapshot_sha=hashlib.sha256(binary).hexdigest()
    if expected_snapshot_sha256 is not None and snapshot_sha!=expected_snapshot_sha256:
        raise ValueError("detached Player export differs from independent SHA-256")
    parsed=parse_private_detached_step1_snapshot(binary)

    image=png.read_bytes()
    if not 0<len(image)<=MAX_PNG_BYTES:
        raise ValueError("Player screenshot PNG changed length during read")
    png_sha=hashlib.sha256(image).hexdigest()
    if expected_png_sha256 is not None and png_sha!=expected_png_sha256:
        raise ValueError("Player PNG differs from independent SHA-256")
    dimensions,rgb=decode_private_opaque_rgb_png(image)
    if any(type(n) is not int for n in (x,y,width,height)) or dimensions!=(width,height):
        raise ValueError("detached Player PNG must have exact unscaled ROI dimensions")
    matching=compare_private_rewind_vram_rgb(parsed["raw"],rgb,x,y,width,height)
    delta=first_step_change_summary(before,parsed["raw"],
                                    x=x,y=y,width=width,height=height)
    if require_changed_roi and not delta["roi_visibly_changed_rgb555_pixel_count"]:
        raise ValueError("Step 1 exported ROI shows no visible change from Rewind")
    if require_exact_rgb and not matching["rgb_pixel_values_exactly_equal"]:
        raise ValueError("Step 1 PNG RGB differs from detached exported VRAM")

    return {
        "kind":"WA1_PRIVATE_DETACHED_GPUDUMP_PLAYER_STEP1_EXPORT_AUDIT",
        "schema":1,
        "status":(
            "PATCHED_PLAYER_STEP1_CONTAINER_RGB_EQUALITY_DUMP_LINK_UNVERIFIED"
            if matching["rgb_pixel_values_exactly_equal"] else
            "PATCHED_PLAYER_STEP1_CONTAINER_RGB_MISMATCH_NO_VISUAL_BINDING"),
        "native_gpudump_sha256":binding["native_dump_sha256"],
        "native_gp0_jsonl_sha256":binding["imported_gp0_jsonl_sha256"],
        "native_pretrace_vram_sha256":binding["imported_prepacket_vram_sha256"],
        "native_first_vsync_gpu_cycle":binding["native_first_frame_ended_at_gpu_cycle"],
        "exported_snapshot_file_sha256":snapshot_sha,
        "exported_snapshot_vram_sha256":parsed["vram_sha256"],
        "owner_player_png_sha256":png_sha,
        "exported_player_frame_from_container":parsed["frame"],
        "exported_vram_byte_count":VRAM_BYTES,
        "exported_vram_crc32_verified":parsed["crc32_verified"],
        "roi_exact_rgb_equal":matching["rgb_pixel_values_exactly_equal"],
        "roi_compared_pixel_count":matching["compared_rgb_pixel_count"],
        "roi_mismatched_pixel_count":matching["mismatched_rgb_pixel_count"],
        "change_from_native_pretrace":delta,
        "interpretation":{
            "player_frame_label_and_vram_captured_atomically_in_one_file":True,
            "container_crc32_detects_accidental_transport_corruption_only":True,
            "patched_player_build_is_not_attested_by_this_tool":True,
            "container_does_not_authenticate_loaded_native_dump_identity":True,
            "operator_must_independently_verify_same_dump_loaded_in_player":True,
            "png_provenance_from_player_ui_remains_unattested":True,
            "not_an_independent_gpu_rasterizer":True,
            "native_scene_disc_camera_and_software_gpu_output_not_authenticated":True,
            "raw_original_vram_gp0_png_pixels_and_game_id_not_exported":True,
            "all_hashes_and_reports_remain_owner_private":True,
        },
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_gpu_dump")
    parser.add_argument("private_original_pretrace_vram")
    parser.add_argument("private_imported_gp0_jsonl")
    parser.add_argument("private_patched_player_step1_export")
    parser.add_argument("private_player_step1_unscaled_png_roi")
    for n in ("x","y","width","height"):
        parser.add_argument("--"+n,type=int,required=True)
    parser.add_argument("--expected-snapshot-sha256")
    parser.add_argument("--expected-png-sha256")
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-frame",type=int)
    parser.add_argument("--require-changed-roi",action="store_true")
    parser.add_argument("--allow-rgb-mismatch",action="store_true")
    args=parser.parse_args()
    report=verify_private_detached_step1_export(
        args.private_native_gpu_dump,
        args.private_original_pretrace_vram,
        args.private_imported_gp0_jsonl,
        args.private_patched_player_step1_export,
        args.private_player_step1_unscaled_png_roi,
        x=args.x,y=args.y,width=args.width,height=args.height,
        expected_snapshot_sha256=args.expected_snapshot_sha256,
        expected_png_sha256=args.expected_png_sha256,
        expected_native_sha256=args.expected_native_sha256,
        expected_frame=args.expected_frame,
        require_changed_roi=args.require_changed_roi,
        require_exact_rgb=not args.allow_rgb_mismatch)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
