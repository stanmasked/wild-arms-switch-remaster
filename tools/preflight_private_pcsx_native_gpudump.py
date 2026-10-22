#!/usr/bin/env python3
"""Owner-private PCSX-Redux native GPU dump preflight, even when replay fails.

Strict typed framing comes from Stage447's pinned native GPUDUMP parser.
This is DIAGNOSTIC ONLY: it cannot verify emulator binary revision,
game/map provenance, native vsync-camera identity, GP0 rasterization
or GPU cache behavior. Emits no actual GPU commands or game pixels.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from import_private_pcsx_native_gpudump import (
    MAX_DUMP_BYTES, GP0, GP1, VSYNC, THROWAWAY, READBACK,
    TRACE_BEGIN, GPU_VERSION, GAME_ID, VIDEO_FORMAT, COMMENT,
    read_native_gpu_dump, select_first_native_gp0_frame,
)
from audit_private_pcsx_native_vsync_chronology import (
    inspect_native_vsync_chronology,
)

NAMES = {
    GP0:"GP0", GP1:"GP1", VSYNC:"VSYNC", THROWAWAY:"THROWAWAY",
    READBACK:"READBACK", TRACE_BEGIN:"TRACE_BEGIN",
    GPU_VERSION:"GPU_VERSION", GAME_ID:"GAME_ID",
    VIDEO_FORMAT:"VIDEO_FORMAT", COMMENT:"COMMENT",
}


def summarize_private_native_gpudump(blob, *, max_frame_summaries=12):
    """Return bounded metadata, no source words and no game-ID payload.

    Native records need not align with GP0 commands; counts are
    transport records, not GPU primitive/packet counts.
    """
    if (type(max_frame_summaries) is not int or
            not 1 <= max_frame_summaries <= 64):
        raise ValueError("invalid private frame summary limit")
    records=read_native_gpu_dump(blob)
    # This is independent of the first-frame GPU command-subset verdict:
    # a valid first frame can still coexist with an incomplete final tail.
    chronology=inspect_native_vsync_chronology(records)
    total=Counter()
    bootstrap=Counter()
    frames=[]
    current=Counter()
    saw_begin=False
    prelude_vsync_count=0
    after_frames=0
    for kind, words in records:
        name=NAMES[kind]
        total[name+"_records"]+=1
        total[name+"_words"]+=len(words)
        if kind==TRACE_BEGIN:
            if not saw_begin:
                saw_begin=True
            else:
                # Stage447 will reject repeated TraceBegin; it must not
                # accidentally enter frame counters as a normal record.
                current["TRACE_BEGIN_REPEATED"]+=1
            continue
        if not saw_begin:
            bootstrap[name+"_records"]+=1
            bootstrap[name+"_words"]+=len(words)
            if kind==VSYNC:
                prelude_vsync_count+=1
            continue
        if kind==VSYNC:
            after_frames+=1
            if len(frames)<max_frame_summaries:
                frames.append({
                    "zero_based_native_frame_index":after_frames-1,
                    "gp0_transport_record_count":current["GP0_records"],
                    "gp0_word_count":current["GP0_words"],
                    "gp1_transport_record_count":current["GP1_records"],
                    "gp1_word_count":current["GP1_words"],
                    "readback_record_count":current["READBACK_records"],
                    "throwaway_record_count":current["THROWAWAY_records"],
                    "repeated_trace_begin_count":current["TRACE_BEGIN_REPEATED"],
                    "unsupported_live_gpu_side_events_present":bool(
                        current["GP1_records"] or current["READBACK_records"] or
                        current["THROWAWAY_records"] or
                        current["TRACE_BEGIN_REPEATED"]),
                })
            current=Counter()
        else:
            current[name+"_records"]+=1
            current[name+"_words"]+=len(words)
    if not saw_begin:
        diagnostic="NO_NATIVE_TRACE_BEGIN"
        compatible=False
    else:
        try:
            first=select_first_native_gp0_frame(records)
        except ValueError as exc:
            # Errors are structural labels and supported GPU opcodes,
            # not copies of raw words or original source bytes.
            diagnostic=str(exc)
            compatible=False
        else:
            diagnostic="SUPPORTED_MODELED_FIRST_FRAME"
            compatible=True
    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PCSX_NATIVE_GPUDUMP_PREFLIGHT",
        "native_vsync_chronology":chronology,
        "native_dump_sha256":hashlib.sha256(blob).hexdigest(),
        "native_dump_byte_count":len(blob),
        "native_typed_record_count":len(records),
        "native_record_type_counts":dict(sorted(total.items())),
        "bootstrap_type_counts":dict(sorted(bootstrap.items())),
        "trace_begin_marker_seen":saw_begin,
        "vsync_before_trace_begin_count":prelude_vsync_count,
        "completed_native_frame_count":after_frames,
        "sampled_frame_count":len(frames),
        "frame_samples_truncated":after_frames>len(frames),
        "frame_summaries":frames,
        "open_trailing_frame_events":dict(sorted(current.items()))
            if saw_begin else None,
        "first_frame_import_accepted_by_stage447_subset":compatible,
        "first_frame_import_diagnostic":diagnostic,
        "interpretation":{
            "actual_first_frame_native_gp0_writes_not_guaranteed_supported":True,
            "first_frame_compatibility_only_not_emulator_attestation":True,
            "record_boundaries_not_gp0_primitive_boundaries":True,
            "bootstrap_full_vram_is_not_original_live_frame_traffic":True,
            "emulator_version_and_original_disc_not_authenticated":True,
            "no_original_gpu_words_vram_image_game_id_or_pixels_emitted":True,
            "native_dump_and_all_metadata_must_remain_private":True,
        },
    }


def preflight_private_native_gpudump(path, *, max_frame_summaries=12):
    target=Path(path)
    if (target.is_symlink() or not target.is_file() or
            not 20<=target.stat().st_size<=MAX_DUMP_BYTES):
        raise ValueError("invalid owner-private native GPU dump file")
    payload=target.read_bytes()
    if not 20<=len(payload)<=MAX_DUMP_BYTES:
        raise ValueError("owner-private GPU dump changed size during read")
    return summarize_private_native_gpudump(
        payload,max_frame_summaries=max_frame_summaries)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_pcsx_gpudump",type=Path)
    parser.add_argument("--max-frame-summaries",type=int,default=12)
    args=parser.parse_args()
    print(json.dumps(preflight_private_native_gpudump(
        args.private_native_pcsx_gpudump,
        max_frame_summaries=args.max_frame_summaries),
        indent=2,sort_keys=True))


if __name__=="__main__":
    main()
