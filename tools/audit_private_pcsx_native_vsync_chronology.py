#!/usr/bin/env python3
"""OWNER-PRIVATE VSync chronology diagnostics for a native PCSX-Redux GPU dump.

PCSX-Redux stores a pair of u32 words with every native VSync record
(low 32 bits, then high 32 bits of a 64-bit GPU cycle stamp). Stage447
uses the FIRST completed VSync for a modeled frame. This tool examines
the WHOLE typed dump for duplicate TraceBegin, out-of-order VSync
timestamps, and data after the last completed VSync.

No actual graphics, GP0 words, CD serial, raw VRAM or game pixels are
exported. Timestamps/metadata and hashes remain private. Cycle order
is not proof of emulator authenticity, wall-clock time, or frame rate.
"""
import argparse
import hashlib
import json
from pathlib import Path

from import_private_pcsx_native_gpudump import (
    MAX_DUMP_BYTES, TRACE_BEGIN, VSYNC, GP0, GP1,
    READBACK, THROWAWAY, read_native_gpu_dump,
)

LIVE_GPU_TYPES=frozenset((GP0,GP1,READBACK,THROWAWAY))
MAX_SAMPLE=64


def inspect_native_vsync_chronology(records, *, max_interval_samples=16,
                                    expected_completed_frames=None):
    if (type(records) is not list or
            type(max_interval_samples) is not int or
            not 1 <= max_interval_samples <= MAX_SAMPLE or
            (expected_completed_frames is not None and
             (type(expected_completed_frames) is not int or
              not 1 <= expected_completed_frames <= 20000))):
        raise ValueError("invalid native VSync chronology arguments")
    trace_begin_indices=[]
    native_vsync_stamps=[]
    vsync_indices=[]
    for idx,record in enumerate(records):
        if (type(record) is not tuple or len(record)!=2 or
                type(record[0]) is not int or
                not isinstance(record[1],(tuple,list))):
            raise ValueError("invalid native typed record in chronology")
        kind,words=record
        if kind==TRACE_BEGIN:
            trace_begin_indices.append(idx)
            if words:
                raise ValueError("TraceBegin cannot carry GPU data words")
        if kind==VSYNC:
            if len(words)!=2 or any(type(v) is not int or
                                    not 0 <= v <= 0xffffffff for v in words):
                raise ValueError("native VSync cycle stamp must be two u32")
            vsync_indices.append(idx)
            native_vsync_stamps.append(words[0] | words[1]<<32)

    first_trace=trace_begin_indices[0] if trace_begin_indices else None
    first_live_vsync_idx=next((
        index for index in range(len(vsync_indices))
        if first_trace is not None and vsync_indices[index]>first_trace),
        None)
    completed_stamps=(native_vsync_stamps[first_live_vsync_idx:]
                      if first_live_vsync_idx is not None else [])
    prelude_vs=len(native_vsync_stamps)-len(completed_stamps)
    deltas=[b-a for a,b in zip(completed_stamps,completed_stamps[1:])]
    nonmonotonic=sum(value<=0 for value in deltas)
    trailing=records[vsync_indices[-1]+1:] if vsync_indices else []
    trailing_gpu=sum(kind in LIVE_GPU_TYPES for kind,_ in trailing)
    missing_start=len(trace_begin_indices)!=1
    expected_matches=(expected_completed_frames is None or
                      len(completed_stamps)==expected_completed_frames)
    # Starting a new GPU frame after its last completed VSync means it
    # may be an unfinished final fragment, NOT a complete frame.
    ended_on_vsync=(bool(records) and records[-1][0]==VSYNC)
    boundaries_valid=bool(
        not missing_start and prelude_vs==0 and completed_stamps and
        nonmonotonic==0 and expected_matches)
    strictly_complete=bool(boundaries_valid and ended_on_vsync)
    status=(
        "TRACE_BEGIN_MISSING_OR_DUPLICATE" if missing_start else
        "PRELUDE_VSYNC_BEFORE_TRACE_BEGIN" if prelude_vs else
        "NO_COMPLETED_POST_TRACE_VSYNC" if not completed_stamps else
        "NONMONOTONIC_VSYNC_CYCLE_STAMPS" if nonmonotonic else
        "UNEXPECTED_COMPLETED_FRAME_COUNT" if not expected_matches else
        "TRAILING_PARTIAL_NATIVE_FRAME" if not ended_on_vsync else
        "COMPLETE_VSYNC_BOUNDARIES_IN_TYPED_DUMP")
    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PCSX_NATIVE_GPUDUMP_VSYNC_CHRONOLOGY",
        "chronology_status":status,
        "trace_begin_marker_count":len(trace_begin_indices),
        "prelude_vsync_record_count":prelude_vs,
        "completed_post_trace_vsync_count":len(completed_stamps),
        "non_increasing_vsync_interval_count":nonmonotonic,
        "first_vsync_cycle_stamp":
            completed_stamps[0] if completed_stamps else None,
        "last_vsync_cycle_stamp":
            completed_stamps[-1] if completed_stamps else None,
        "minimum_vsync_cycle_delta":min(deltas) if deltas else None,
        "maximum_vsync_cycle_delta":max(deltas) if deltas else None,
        "first_vsync_cycle_delta_samples":deltas[:max_interval_samples],
        "vsync_delta_samples_truncated":len(deltas)>max_interval_samples,
        "event_records_after_last_vsync":len(trailing),
        "live_gpu_transport_records_after_last_vsync":trailing_gpu,
        "last_typed_record_is_vsync":ended_on_vsync,
        "independently_expected_completed_frame_count_compared":
            expected_completed_frames is not None,
        "expected_completed_frame_count_matches":expected_matches,
        "all_completed_vsync_stamps_strictly_increasing":nonmonotonic==0,
        "native_typed_boundaries_chronologically_coherent":boundaries_valid,
        "native_dump_ends_on_complete_vsync_record":strictly_complete,
        "interpretation":{
            "vblank_cycle_values_are_emulator_clock_ticks_not_wall_time":True,
            "monotonic_vsync_does_not_authenticate_emulator_executable":True,
            "whole_dump_record_boundaries_not_proof_of_gp0_packet_completeness":True,
            "first_frame_gp0_model_support_not_checked_here":True,
            "multi_frame_gpu_rasterization_not_performed":True,
            "raw_original_disc_pixels_gpu_words_and_game_id_not_exported":True,
            "all_timing_metadata_must_remain_owner_private":True,
        },
    }


def audit_private_native_vsync(path, *, max_interval_samples=16,
                               expected_completed_frames=None,
                               require_complete_vsync_end=False):
    target=Path(path)
    if (type(require_complete_vsync_end) is not bool or target.is_symlink()
            or not target.is_file()
            or not 20 <= target.stat().st_size <= MAX_DUMP_BYTES):
        raise ValueError("invalid owner-private native GPU dump path")
    data=target.read_bytes()
    if not 20 <= len(data) <= MAX_DUMP_BYTES:
        raise ValueError("native dump changed size during read")
    report=inspect_native_vsync_chronology(
        read_native_gpu_dump(data),
        max_interval_samples=max_interval_samples,
        expected_completed_frames=expected_completed_frames)
    report["native_dump_sha256"]=hashlib.sha256(data).hexdigest()
    if (require_complete_vsync_end and
            not report["native_dump_ends_on_complete_vsync_record"]):
        raise ValueError("native dump has unverified VSync frame chronology: "+
                         report["chronology_status"])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_gpudump",type=Path)
    parser.add_argument("--max-interval-samples",type=int,default=16)
    parser.add_argument("--expected-completed-frames",type=int)
    parser.add_argument("--require-complete-vsync-end",action="store_true")
    args=parser.parse_args()
    print(json.dumps(audit_private_native_vsync(
        args.private_native_gpudump,
        max_interval_samples=args.max_interval_samples,
        expected_completed_frames=args.expected_completed_frames,
        require_complete_vsync_end=args.require_complete_vsync_end),
        indent=2,sort_keys=True))


if __name__=="__main__":
    main()
