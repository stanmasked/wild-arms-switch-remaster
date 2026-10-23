#!/usr/bin/env python3
"""Verify Frame-1 detached Player VRAM bound to the exact loaded native dump SHA-256.

Owner-private, synthetic tests only in public CI. The source hash in the
container is captured by the patched PCSX-Redux GPUDumpReader when it reads
the native file; it is not an independent attestation of the patched binary.
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

MAGIC=b"WA1STEPVRAMv2\x00\x00\x00"
HEADER=struct.Struct("<16sQII32s")
MAX_PNG_BYTES=16*1024*1024
SHA256=re.compile(r"[0-9a-f]{64}")


def parse_private_dump_hash_bound_step1(binary):
    if type(binary) is not bytes or len(binary)!=HEADER.size+VRAM_BYTES:
        raise ValueError("dump-bound Step 1 export must contain exactly 64 + 1048576 bytes")
    magic,frame,length,checksum,dump_digest=HEADER.unpack_from(binary)
    if magic!=MAGIC:
        raise ValueError("unknown or corrupt dump-bound Player export magic/version")
    if frame!=1:
        raise ValueError("dump-bound detached GPU export is not Player Frame 1")
    if length!=VRAM_BYTES:
        raise ValueError("invalid declared dump-bound detached Player VRAM length")
    raw=binary[HEADER.size:]
    if zlib.crc32(raw)&0xffffffff != checksum:
        raise ValueError("dump-bound detached Player VRAM CRC32 mismatch")
    return {
        "frame":frame,
        "native_dump_sha256":dump_digest.hex(),
        "vram_sha256":hashlib.sha256(raw).hexdigest(),
        "raw":raw,
        "crc32_verified":True,
    }


def verify_private_dump_hash_bound_step1_export(
        native_path,initial_path,gp0_trace_path,snapshot_path,png_path,*,
        x,y,width,height,expected_snapshot_sha256=None,
        expected_png_sha256=None,expected_native_sha256=None,
        expected_frame=None,require_changed_roi=False,require_exact_rgb=True):
    if type(require_changed_roi) is not bool or type(require_exact_rgb) is not bool:
        raise ValueError("strict replay comparison options must be booleans")
    for name,value in (("snapshot",expected_snapshot_sha256),
                       ("PNG",expected_png_sha256),
                       ("native",expected_native_sha256)):
        if value is not None and (type(value) is not str or SHA256.fullmatch(value) is None):
            raise ValueError(name+" SHA-256 expectation must be lowercase 64 hex")
    source,initial,trace,snapshot,png=map(
        Path,(native_path,initial_path,gp0_trace_path,snapshot_path,png_path))
    paths=(source,initial,trace,snapshot,png)
    if (len(set(map(str,paths)))!=5 or
        any(p.is_symlink() or not p.is_file() for p in paths) or
        snapshot.stat().st_size!=HEADER.size+VRAM_BYTES or
        not 0<png.stat().st_size<=MAX_PNG_BYTES):
        raise ValueError("invalid or aliased private dump-bound Player export inputs")

    binding=bind_private_first_frame_capture(
        source,initial,trace,
        expected_native_sha256=expected_native_sha256,
        expected_frame=expected_frame)
    native_digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if native_digest!=binding["native_dump_sha256"]:
        raise ValueError("native GPU dump changed after first-frame binding")
    if hashlib.sha256(initial.read_bytes()).hexdigest()!=binding["imported_prepacket_vram_sha256"]:
        raise ValueError("initial VRAM changed after native binding")

    binary=snapshot.read_bytes()
    if len(binary)!=HEADER.size+VRAM_BYTES:
        raise ValueError("dump-bound Player export changed length during read")
    snapshot_sha=hashlib.sha256(binary).hexdigest()
    if expected_snapshot_sha256 is not None and snapshot_sha!=expected_snapshot_sha256:
        raise ValueError("dump-bound Player export differs from independent SHA-256")
    parsed=parse_private_dump_hash_bound_step1(binary)
    if parsed["native_dump_sha256"]!=native_digest:
        raise ValueError("snapshot's loaded native dump SHA-256 does not match supplied native dump")

    image=png.read_bytes()
    if not 0<len(image)<=MAX_PNG_BYTES:
        raise ValueError("Player PNG invalid size")
    png_sha=hashlib.sha256(image).hexdigest()
    if expected_png_sha256 is not None and png_sha!=expected_png_sha256:
        raise ValueError("Player PNG differs from independent SHA-256")
    dimensions,rgb=decode_private_opaque_rgb_png(image)
    if any(type(n) is not int for n in (x,y,width,height)) or dimensions!=(width,height):
        raise ValueError("dump-bound Player PNG must have exact unscaled ROI dimensions")
    matching=compare_private_rewind_vram_rgb(parsed["raw"],rgb,x,y,width,height)
    delta=first_step_change_summary(initial.read_bytes(),parsed["raw"],
                                    x=x,y=y,width=width,height=height)
    if require_changed_roi and not delta["roi_visibly_changed_rgb555_pixel_count"]:
        raise ValueError("dump-bound Step 1 ROI shows no visible change from Rewind")
    if require_exact_rgb and not matching["rgb_pixel_values_exactly_equal"]:
        raise ValueError("dump-bound Step 1 PNG RGB differs from exported VRAM")

    return {
        "kind":"WA1_PRIVATE_DUMP_HASH_BOUND_GPUDUMP_PLAYER_STEP1_AUDIT",
        "schema":1,
        "status":(
            "PLAYER_STEP1_NATIVE_DUMP_HASH_BOUND_RGB_EQUALITY_BUILD_UNATTESTED"
            if matching["rgb_pixel_values_exactly_equal"] else
            "PLAYER_STEP1_NATIVE_DUMP_HASH_BOUND_RGB_MISMATCH_NO_VISUAL_BINDING"),
        "native_gpudump_sha256":native_digest,
        "snapshot_native_gpudump_sha256":parsed["native_dump_sha256"],
        "snapshot_native_dump_sha256_matches":True,
        "native_gp0_jsonl_sha256":binding["imported_gp0_jsonl_sha256"],
        "native_pretrace_vram_sha256":binding["imported_prepacket_vram_sha256"],
        "native_first_vsync_gpu_cycle":binding["native_first_frame_ended_at_gpu_cycle"],
        "snapshot_file_sha256":snapshot_sha,
        "snapshot_vram_sha256":parsed["vram_sha256"],
        "player_png_sha256":png_sha,
        "player_frame_from_snapshot":parsed["frame"],
        "exported_vram_byte_count":VRAM_BYTES,
        "exported_vram_crc32_verified":parsed["crc32_verified"],
        "roi_exact_rgb_equal":matching["rgb_pixel_values_exactly_equal"],
        "roi_compared_pixel_count":matching["compared_rgb_pixel_count"],
        "roi_mismatched_pixel_count":matching["mismatched_rgb_pixel_count"],
        "change_from_native_pretrace":delta,
        "interpretation":{
            "player_frame_vram_and_loaded_dump_digest_captured_in_same_patched_player":True,
            "native_dump_identity_is_bound_by_sha256_from_reader_input":True,
            "snapshot_sha256_does_not_attest_the_emulator_build_or_patch":True,
            "container_crc32_is_transport_integrity_not_authentication":True,
            "operator_supplied_png_origin_remains_unattested":True,
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
    parser.add_argument("private_player_step1_dump_bound_export")
    parser.add_argument("private_player_step1_unscaled_png_roi")
    for name in ("x","y","width","height"):
        parser.add_argument("--"+name,type=int,required=True)
    parser.add_argument("--expected-snapshot-sha256")
    parser.add_argument("--expected-png-sha256")
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-frame",type=int)
    parser.add_argument("--require-changed-roi",action="store_true")
    parser.add_argument("--allow-rgb-mismatch",action="store_true")
    args=parser.parse_args()
    report=verify_private_dump_hash_bound_step1_export(
        args.private_native_gpu_dump,args.private_original_pretrace_vram,
        args.private_imported_gp0_jsonl,args.private_player_step1_dump_bound_export,
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
