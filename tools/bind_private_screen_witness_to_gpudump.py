#!/usr/bin/env python3
"""OWNER-PRIVATE paused screenshot witness vs native GPUDUMP starting VRAM.

Stage432 screenshot/CD/VRAM witness is taken from a PAUSED emulator via
read-only PCSX-Redux REST. Stage451 native GPUDUMP binds first-frame GP0
commands to the native pretrace VRAM and VSync chronology.

This checks *only* byte-exact equality of their starting VRAM states.
Even matching 1 MiB does NOT prove the screenshot and native GP0 frame
were captured simultaneously or that either is genuine Surf Village.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from capture_private_pcsx_frame_witness import verify_private_frame_witness
from capture_private_pcsx_redux_vram import _validate_basename
from bind_private_pcsx_first_frame_evidence import bind_private_first_frame_capture

_HEX_SHA = re.compile(r"[0-9a-f]{64}")


def bind_private_screen_witness_to_gpu_dump(
        witness_directory, witness_basename, native_gpudump,
        native_initial_vram, imported_gp0_trace, *,
        require_exact_vram_match=True,
        require_complete_native_capture=True,
        expected_screen_sha256=None, expected_native_sha256=None,
        expected_native_game_id=None, expected_frame=None,
        expected_completed_frames=None):
    """Compare complete verified witness/snapshot states, not inferred frames."""
    _validate_basename(witness_basename)
    if (type(require_exact_vram_match) is not bool or
            type(require_complete_native_capture) is not bool or
            (expected_screen_sha256 is not None and
             (type(expected_screen_sha256) is not str or
              _HEX_SHA.fullmatch(expected_screen_sha256) is None))):
        raise ValueError("invalid strict-state or screen SHA256 expectation")
    witness_root=Path(witness_directory)
    if witness_root.is_symlink() or not witness_root.is_dir():
        raise ValueError("invalid private Stage432 witness directory")

    # Verify screen PNG framing/CRC, CD-info JSON, two-read VRAM hash and
    # exact Stage432 manifest-controlled artifact paths, not just filenames.
    before=verify_private_frame_witness(
        witness_root,basename=witness_basename)
    if not before["verified"]:
        raise ValueError("paused screen witness failed Stage432 verification")
    if (expected_screen_sha256 is not None and
            before["screen_sha256"] != expected_screen_sha256):
        raise ValueError("paused witness screen differs from expected screenshot SHA256")

    # Stage451 independently rechecks native file identity three times,
    # the complete initial VRAM, all GP0 words and native VSync order.
    native=bind_private_first_frame_capture(
        native_gpudump,native_initial_vram,imported_gp0_trace,
        expected_native_sha256=expected_native_sha256,
        expected_native_game_id=expected_native_game_id,
        expected_frame=expected_frame,
        expected_completed_frames=expected_completed_frames,
        require_complete_capture=require_complete_native_capture)

    # Catch accidental changes to *all three* Stage432 assets while
    # native integrity tests are running; does not defeat malicious races.
    after=verify_private_frame_witness(
        witness_root,basename=witness_basename)
    for field in ("vram_sha256","screen_sha256","cd_info_sha256"):
        if before[field] != after[field]:
            raise ValueError("paused Stage432 witness changed during GPU-dump analysis")

    same_state=(
        before["vram_sha256"]==native["imported_prepacket_vram_sha256"])
    if require_exact_vram_match and not same_state:
        raise ValueError(
            "paused screenshot witness VRAM differs from native GPUDUMP pretrace VRAM")

    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PAUSED_SCREEN_TO_NATIVE_GPUDUMP_VRAM_STATE",
        "status":(
            "EXACT_VRAM_STATE_EQUALITY_WITH_UNVERIFIED_FRAME_ALIGNMENT"
            if same_state else
            "DIFFERENT_VRAM_STATES_NO_FRAME_BINDING"
        ),
        "owner_witness_basename":witness_basename,
        "native_gpudump_sha256":native["native_dump_sha256"],
        "native_first_vsync_cycle_stamp":
            native["native_first_frame_ended_at_gpu_cycle"],
        "native_completed_frame_count":native["native_completed_frame_count"],
        "stage437_operator_frame_label":native["stage437_operator_frame_label"],
        "paused_witness_vram_sha256":before["vram_sha256"],
        "native_initial_vram_sha256":
            native["imported_prepacket_vram_sha256"],
        "paused_screenshot_png_sha256":before["screen_sha256"],
        "paused_disc_info_sha256":before["cd_info_sha256"],
        "imported_gp0_jsonl_sha256":native["imported_gp0_jsonl_sha256"],
        "paused_and_native_initial_vram_sha256_equal":same_state,
        "exact_vram_equality_required":require_exact_vram_match,
        "complete_native_capture_required":require_complete_native_capture,
        "native_gp0_vram_vsync_binding_verified":True,
        "stage432_screen_png_disc_and_vram_integrity_verified_twice":True,
        "independent_expected_screen_hash_compared":
            expected_screen_sha256 is not None,
        "native_capture_whole_dump_vsync_end_verified":
            native["whole_native_dump_ends_at_vsync_boundary"],
        "interpretation":{
            "equal_vram_states_are_not_proof_of_same_frame":True,
            "same_texture_memory_may_recur_at_different_game_times":True,
            "screenshot_render_may_precede_pause_and_gpu_capture":True,
            "native_first_vsync_not_proven_same_as_paused_screenshot":True,
            "operator_scene_label_is_not_authenticated_map_identity":True,
            "disc_info_fingerprint_not_independent_disc_attestation":True,
            "gpu_texture_clut_caches_and_rasterization_unmodeled":True,
            "original_screenshot_pixels_vram_gp0_words_and_disc_info_not_emitted":True,
            "all_hashes_and_witness_metadata_remain_owner_private":True,
        },
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_stage432_witness_directory")
    parser.add_argument("owner_private_stage432_witness_basename")
    parser.add_argument("owner_private_native_gpudump")
    parser.add_argument("owner_private_native_prepacket_vram")
    parser.add_argument("owner_private_native_first_frame_gp0_jsonl")
    parser.add_argument("--allow-different-vram-states",action="store_true")
    parser.add_argument("--allow-incomplete-native-capture",action="store_true")
    parser.add_argument("--expected-screen-sha256")
    parser.add_argument("--expected-native-sha256")
    parser.add_argument("--expected-native-game-id")
    parser.add_argument("--expected-frame",type=int)
    parser.add_argument("--expected-completed-frames",type=int)
    args=parser.parse_args()
    report=bind_private_screen_witness_to_gpu_dump(
        args.owner_private_stage432_witness_directory,
        args.owner_private_stage432_witness_basename,
        args.owner_private_native_gpudump,
        args.owner_private_native_prepacket_vram,
        args.owner_private_native_first_frame_gp0_jsonl,
        require_exact_vram_match=not args.allow_different_vram_states,
        require_complete_native_capture=not args.allow_incomplete_native_capture,
        expected_screen_sha256=args.expected_screen_sha256,
        expected_native_sha256=args.expected_native_sha256,
        expected_native_game_id=args.expected_native_game_id,
        expected_frame=args.expected_frame,
        expected_completed_frames=args.expected_completed_frames)
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
