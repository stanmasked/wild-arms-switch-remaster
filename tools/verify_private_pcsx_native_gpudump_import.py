#!/usr/bin/env python3
"""Owner-private native GPU dump -> extracted VRAM/GP0 JSONL roundtrip audit.

Rebuild Stage447's first-frame packets from the SAME original native dump,
then compare *all* packet words and the exact pretrace VRAM bytes to
independently saved Stage447 outputs. Optional operator GameID and
out-of-band dump digest checks are conditional sanity checks, never
proof of genuine Wild Arms map, emulator binary or GPU rasterization.

Run ONLY on the owner's machine. Never upload source dumps or reports.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from audit_private_gp0_upload_timeline import (
    MAX_TRACE_BYTES, VRAM_BYTES, read_private_gp0_timeline,
)
from import_private_pcsx_native_gpudump import (
    GAME_ID, TRACE_BEGIN, MAX_DUMP_BYTES,
    read_native_gpu_dump, select_first_native_gp0_frame,
)
from package_private_raw_gp0_wordstream import packetize_owner_raw_words

MAX_GAME_ID_BYTES=64


def _native_game_id(records):
    """Return optional exact zero-padded native GameID, never expose in result."""
    seen=False
    value=None
    before_trace=True
    for kind, words in records:
        if kind == TRACE_BEGIN:
            before_trace=False
        if kind != GAME_ID:
            continue
        if not before_trace or seen or not 1 <= len(words) <= MAX_GAME_ID_BYTES//4+1:
            raise ValueError("missing preamble-only unique GameID contract")
        seen=True
        raw=b"".join(word.to_bytes(4,"little") for word in words)
        ending=raw.find(b"\0")
        if ending == -1 or ending == 0 or any(raw[ending:]):
            raise ValueError("native GameID must be nonempty and zero-padded")
        raw_id=raw[:ending]
        if len(raw_id)>MAX_GAME_ID_BYTES or any(
                byte < 33 or byte > 126 for byte in raw_id):
            raise ValueError("invalid printable ASCII native GameID")
        value=raw_id.decode("ascii")
    return value


def verify_private_native_import(
        native_path, initial_vram_path, gp0_jsonl_path, *,
        expected_native_game_id=None, expected_native_sha256=None,
        expected_frame=None):
    """Verify ALL exact words and bytes of one Stage447 first-frame import."""
    if expected_native_game_id is not None and (
            type(expected_native_game_id) is not str or
            not 1 <= len(expected_native_game_id) <= MAX_GAME_ID_BYTES or
            any(ord(char)<33 or ord(char)>126
                for char in expected_native_game_id)):
        raise ValueError("expected native game ID must be printable ASCII")
    if expected_native_sha256 is not None and (
            type(expected_native_sha256) is not str or
            not re.fullmatch(r"[0-9a-f]{64}", expected_native_sha256)):
        raise ValueError("expected native dump SHA256 must be lowercase hex")
    if expected_frame is not None and (
            type(expected_frame) is not int or expected_frame<0):
        raise ValueError("expected trace frame must be nonnegative integer")
    native_path, pre_path, trace_path=map(
        Path,(native_path,initial_vram_path,gp0_jsonl_path))
    paths=(native_path,pre_path,trace_path)
    if (any(path.is_symlink() or not path.is_file() for path in paths) or
            len(set(map(str,paths))) != len(paths) or
            not 20 <= native_path.stat().st_size <= MAX_DUMP_BYTES or
            pre_path.stat().st_size != VRAM_BYTES or
            not 0 < trace_path.stat().st_size <= MAX_TRACE_BYTES):
        raise ValueError("invalid or aliased owner-private GPU evidence files")
    native=native_path.read_bytes()
    pre=pre_path.read_bytes()
    if not 20 <= len(native) <= MAX_DUMP_BYTES or len(pre)!=VRAM_BYTES:
        raise ValueError("owner-private input sizes changed during read")
    native_sha=hashlib.sha256(native).hexdigest()
    if expected_native_sha256 is not None and native_sha!=expected_native_sha256:
        raise ValueError("native GPU dump differs from supplied independent SHA256")
    records=read_native_gpu_dump(native)
    recorded_id=_native_game_id(records)
    if expected_native_game_id is not None and recorded_id!=expected_native_game_id:
        raise ValueError("native GameID differs from caller-provided game ID")
    native_frame=select_first_native_gp0_frame(records)
    if pre!=native_frame["initial_vram"]:
        raise ValueError("prepacket VRAM differs from native GPU dump initialization")
    header, actual_packets, actual_trace_sha=read_private_gp0_timeline(
        trace_path,hashlib.sha256(pre).hexdigest())
    if expected_frame is not None and header["frame"]!=expected_frame:
        raise ValueError("Stage437 JSONL frame differs from expected frame number")
    rebuilt_packets, counts=packetize_owner_raw_words(
        native_frame["modeled_gp0_raw"])
    if len(actual_packets)!=len(rebuilt_packets):
        raise ValueError("native GP0 frame packet count differs from saved JSONL")
    for position,(saved, rebuilt) in enumerate(
            zip(actual_packets,rebuilt_packets)):
        if saved!=rebuilt:
            raise ValueError("native GP0 frame packet differs at index %d" % position)
    return {
        "schema":1,
        "kind":"WA1_PRIVATE_NATIVE_GPUDUMP_STAGE447_IMPORT_INTEGRITY",
        "native_dump_sha256":native_sha,
        "initial_vram_sha256":hashlib.sha256(pre).hexdigest(),
        "saved_trace_sha256":actual_trace_sha,
        "stage437_frame_label":header["frame"],
        "exact_preframe_vram_bytes_verified":len(pre),
        "exact_gp0_packet_count_verified":len(rebuilt_packets),
        "live_first_frame_gp0_word_count":native_frame["live_gp0_word_count"],
        "bootstrap_restore_gp0_word_count":native_frame["bootstrap_command_count"],
        "modeled_packet_group_counts":counts,
        "game_id_present_in_native_preamble":recorded_id is not None,
        "independently_expected_game_id_compared":
            expected_native_game_id is not None,
        "independently_expected_dump_digest_compared":
            expected_native_sha256 is not None,
        "all_saved_gp0_packet_words_equal_native_first_frame":True,
        "all_saved_prepacket_vram_bytes_equal_native_snapshot":True,
        "no_native_game_id_gpu_pixels_packet_words_or_vram_emitted":True,
        "operator_expected_game_id_not_authentication_of_original_disc":True,
        "expected_sha_is_consistency_not_trusted_emulator_attestation":True,
        "recorded_first_frame_does_not_authenticate_surf_village_scene":True,
        "gpu_rasterization_and_clut_cache_unverified":True,
        "all_hashes_and_report_must_remain_owner_private":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("native_gpudump")
    p.add_argument("initial_vram_u16le")
    p.add_argument("gp0_jsonl")
    p.add_argument("--expected-native-game-id")
    p.add_argument("--expected-native-sha256")
    p.add_argument("--expected-frame",type=int)
    args=p.parse_args()
    report=verify_private_native_import(
        args.native_gpudump,args.initial_vram_u16le,args.gp0_jsonl,
        expected_native_game_id=args.expected_native_game_id,
        expected_native_sha256=args.expected_native_sha256,
        expected_frame=args.expected_frame)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
