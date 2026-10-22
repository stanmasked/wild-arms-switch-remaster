#!/usr/bin/env python3
"""Owner-private first-frame evidence binding for PCSX-Redux GPU dumps.

Gate together INDEPENDENTLY recomputed:
  Stage449 exact native dump <-> initial VRAM and GP0 JSONL equality;
  Stage448 native first-frame GP0 transport byte count and support;
  Stage450 first VSync and entire native capture chronology.

No claim about original Wild Arms scene, emulator binary attestation,
actual rasterization or texture/CLUT cache. Reports/hashes are PRIVATE.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from verify_private_pcsx_native_gpudump_import import verify_private_native_import
from preflight_private_pcsx_native_gpudump import preflight_private_native_gpudump
from audit_private_pcsx_native_vsync_chronology import audit_private_native_vsync

MAX_MANIFEST_BYTES = 32768


def bind_private_first_frame_capture(
        native_path, initial_vram_path, gp0_trace_path, *,
        expected_native_sha256=None, expected_native_game_id=None,
        expected_frame=None, expected_completed_frames=None,
        require_complete_capture=True):
    """Fail closed for inconsistency, leave partial tail explicitly untrusted."""
    if type(require_complete_capture) is not bool:
        raise ValueError("require_complete_capture must be a bool")

    # Each source API independently validates its inputs. Matching
    # native SHA256 values across three reads guards accidental
    # cross-capture swaps, not adversarial races or spoofed timestamps.
    imported=verify_private_native_import(
        native_path,initial_vram_path,gp0_trace_path,
        expected_native_sha256=expected_native_sha256,
        expected_native_game_id=expected_native_game_id,
        expected_frame=expected_frame)
    preflight=preflight_private_native_gpudump(
        native_path,max_frame_summaries=1)
    chronology=audit_private_native_vsync(
        native_path,max_interval_samples=1,
        expected_completed_frames=expected_completed_frames)

    native_sha=imported["native_dump_sha256"]
    if (native_sha!=preflight["native_dump_sha256"]
            or native_sha!=chronology["native_dump_sha256"]):
        raise ValueError("native GPU dump changed between independent capture audits")
    if not preflight["first_frame_import_accepted_by_stage447_subset"]:
        raise ValueError("first-frame native GP0 command subset not supported")
    if preflight["completed_native_frame_count"] != chronology[
            "completed_post_trace_vsync_count"]:
        raise ValueError("preflight and chronology disagree on native frame count")
    if not preflight["frame_summaries"]:
        raise ValueError("native dump has no complete first frame in preflight")
    if (preflight["frame_summaries"][0]["gp0_word_count"]
            !=imported["live_first_frame_gp0_word_count"]):
        raise ValueError("native first frame word count differs from imported GP0")
    if (not imported["all_saved_gp0_packet_words_equal_native_first_frame"]
            or not imported["all_saved_prepacket_vram_bytes_equal_native_snapshot"]):
        raise ValueError("native import word/VRAM equality not established")
    if not chronology["native_typed_boundaries_chronologically_coherent"]:
        raise ValueError("native frame chronology is not coherent: "+
                         chronology["chronology_status"])
    full_capture=chronology["native_dump_ends_on_complete_vsync_record"]
    if require_complete_capture and not full_capture:
        raise ValueError("complete native capture required: "+
                         chronology["chronology_status"])

    return {
        "schema":1,
        "kind":"WA1_PRIVATE_NATIVE_FIRST_FRAME_CAPTURE_EVIDENCE_BINDING",
        "binding_status":(
            "WHOLE_NATIVE_CAPTURE_BOUND_TO_FIRST_FRAME_IMPORT"
            if full_capture else
            "FIRST_FRAME_BOUND_WITH_UNVERIFIED_TRAILING_NATIVE_EVENTS"
        ),
        "native_dump_sha256":native_sha,
        "imported_prepacket_vram_sha256":imported["initial_vram_sha256"],
        "imported_gp0_jsonl_sha256":imported["saved_trace_sha256"],
        "stage437_operator_frame_label":imported["stage437_frame_label"],
        "native_first_frame_ended_at_gpu_cycle":
            chronology["first_vsync_cycle_stamp"],
        "native_completed_frame_count":
            chronology["completed_post_trace_vsync_count"],
        "whole_native_dump_ends_at_vsync_boundary":full_capture,
        "imported_first_frame_live_gp0_word_count":
            imported["live_first_frame_gp0_word_count"],
        "imported_first_frame_packet_count":
            imported["exact_gp0_packet_count_verified"],
        "native_prepacket_vram_byte_count":
            imported["exact_preframe_vram_bytes_verified"],
        "native_bootstrap_restore_gp0_word_count":
            imported["bootstrap_restore_gp0_word_count"],
        "recorded_native_game_id_present":
            imported["game_id_present_in_native_preamble"],
        "operator_expected_game_id_compared":
            imported["independently_expected_game_id_compared"],
        "operator_expected_native_hash_compared":
            imported["independently_expected_dump_digest_compared"],
        "operator_expected_frame_count_compared":
            chronology["independently_expected_completed_frame_count_compared"],
        "source_preamble_and_first_frame_crosschecked_against_native_dump":True,
        "native_file_sha256_equal_across_all_independent_reads":True,
        "stage448_first_frame_words_match_stage449_reconstruction":True,
        "interpretation":{
            "stage437_frame_label_is_operator_supplied_not_native_frame_time":True,
            "native_first_frame_gpu_cycle_stamp_not_wall_clock_time":True,
            "bootstrap_gpu_restore_words_not_original_gameplay_traffic":True,
            "first_frame_model_not_rasterized_or_proof_of_visible_texture":True,
            "whole_dump_boundary_not_proof_of_gpu_packet_or_emulator_identity":True,
            "owner_expected_game_id_not_original_disc_authentication":True,
            "source_game_scene_and_camera_not_independently_authenticated":True,
            "hash_consistency_not_protection_against_adversarial_mutation":True,
            "original_gpu_words_vram_palette_bytes_and_game_id_not_exported":True,
            "all_hashes_and_metadata_must_remain_owner_private":True,
        },
    }


def write_private_first_frame_binding_manifest(report, output_path):
    """No-clobber owner-private JSON publication with mode 0600."""
    if (type(report) is not dict or
            report.get("kind") !=
                "WA1_PRIVATE_NATIVE_FIRST_FRAME_CAPTURE_EVIDENCE_BINDING"):
        raise ValueError("expected complete Stage451 binding report")
    output=Path(output_path)
    if (output.is_symlink() or output.exists()
            or not output.parent.is_dir()):
        raise ValueError("private manifest output path already exists or is unsafe")
    body=(json.dumps(report,indent=2,sort_keys=True)+"\n").encode("utf-8")
    if not 0<len(body)<=MAX_MANIFEST_BYTES:
        raise ValueError("binding manifest exceeds size limit")
    fd,temporary=tempfile.mkstemp(prefix=".wa1-private-stage451-",
                                  dir=output.parent)
    tmp=Path(temporary)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp,0o600)
        os.link(tmp,output)
    finally:
        tmp.unlink(missing_ok=True)
    return hashlib.sha256(body).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("owner_private_native_gpudump")
    p.add_argument("private_prepacket_vram_u16le")
    p.add_argument("private_gp0_packets_jsonl")
    p.add_argument("--expected-native-sha256")
    p.add_argument("--expected-native-game-id")
    p.add_argument("--expected-frame",type=int)
    p.add_argument("--expected-completed-frames",type=int)
    p.add_argument("--allow-trailing-native-events",action="store_true")
    p.add_argument("--private-manifest-out")
    args=p.parse_args()
    report=bind_private_first_frame_capture(
        args.owner_private_native_gpudump,
        args.private_prepacket_vram_u16le,
        args.private_gp0_packets_jsonl,
        expected_native_sha256=args.expected_native_sha256,
        expected_native_game_id=args.expected_native_game_id,
        expected_frame=args.expected_frame,
        expected_completed_frames=args.expected_completed_frames,
        require_complete_capture=not args.allow_trailing_native_events)
    if args.private_manifest_out:
        report["private_manifest_sha256"]=write_private_first_frame_binding_manifest(
            report,args.private_manifest_out)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
