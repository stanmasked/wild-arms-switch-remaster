#!/usr/bin/env python3
"""OWNER-PRIVATE native PCSX-Redux GPU dump -> Stage437 first-frame trace.

Based on pinned upstream de4a33e9a69abec4f567ae33567537f867dc2bba
src/core/gpudump.{h,cc}: PSXGPUDUMPv1r1 typed packets, a full VRAM
snapshot and GPU environment restore before TraceBegin, and v-syncs
delimiting live frames. No original GPU dump is uploaded to CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from package_private_raw_gp0_wordstream import (
    package_private_gp0_raw_capture, packetize_owner_raw_words,
)
from audit_private_gp0_upload_timeline import VRAM_BYTES

MAGIC=b"PSXGPUDUMPv1r1\x00\x00"
MAX_DUMP_BYTES=32*1024*1024
FULL_VRAM_A0_WORDS=3+VRAM_BYTES//4
# Native upstream packet types.
GP0,GP1,VSYNC,THROWAWAY,READBACK,TRACE_BEGIN,GPU_VERSION=range(7)
GAME_ID=0x10
VIDEO_FORMAT=0x11
COMMENT=0x12
METADATA_TYPES={GAME_ID,VIDEO_FORMAT,COMMENT}
MAX_NATIVE_PACKET_WORDS=0x400000


def read_native_gpu_dump(native):
    """Read and structurally validate native typed records, fail on truncation."""
    if type(native) is not bytes or not 20 <= len(native) <= MAX_DUMP_BYTES:
        raise ValueError("invalid bounded native GPU dump")
    if native[:16] != MAGIC or len(native)%4:
        raise ValueError("not a complete PSXGPUDUMPv1r1 file")
    offset=16
    result=[]
    while offset < len(native):
        if len(native)-offset < 4:
            raise ValueError("incomplete native GPU dump record header")
        head=struct.unpack_from("<I",native,offset)[0]
        kind,length=head>>24,head&0xffffff
        offset+=4
        if length>MAX_NATIVE_PACKET_WORDS or 4*length>len(native)-offset:
            raise ValueError("truncated or excessive native GPU dump payload")
        if kind not in (GP0,GP1,VSYNC,THROWAWAY,READBACK,TRACE_BEGIN,
                        GPU_VERSION,GAME_ID,VIDEO_FORMAT,COMMENT):
            raise ValueError("unsupported native GPU dump record kind")
        if kind==TRACE_BEGIN and length!=0:
            raise ValueError("native TraceBegin must be empty")
        if kind==VSYNC and length!=2:
            raise ValueError("native VSync must contain one 64-bit cycle stamp")
        if kind==GPU_VERSION and length!=1:
            raise ValueError("native GPUVersion must contain one u32")
        if kind in (GP0,GP1) and length==0:
            raise ValueError("empty native GP0/GP1 record")
        values=struct.unpack_from("<%dI"%length,native,offset) if length else ()
        result.append((kind,values))
        offset+=length*4
        if len(result)>30000:
            raise ValueError("too many native GPU dump records")
    return result


def select_first_native_gp0_frame(records):
    """Separate native pre-trace full VRAM from the first live frame.

    Restore GP0(E1..E6) words are prepended to our modeled frame as an
    explicit bootstrap, not treated as historical live-frame packets.
    We reject all live GP1/readback events unsupported by Stage437.
    """
    if type(records) is not list or not records:
        raise ValueError("native GPU dump has no records")
    version_seen=0
    full_vram_seen=False
    reset_seen=False
    start_seen=False
    vsync_seen=False
    initial_vram=None
    bootstrap=[]
    live=[]
    frame_count=0
    live_gp0_records=0
    metadata_count=0
    # Only a repeated GP1 control that exactly matches pretrace state is
    # safe to omit from Stage437's GP0-only replay. Never infer state from
    # an unobserved register or accept GP1 commands with side effects.
    pretrace_gp1_controls={}
    idempotent_live_gp1_words=0
    for kind,words in records:
        if kind==GPU_VERSION:
            if version_seen or start_seen or tuple(words)!=(2,):
                raise ValueError("missing or unexpected native GPU dump version 2")
            version_seen+=1
        elif kind in METADATA_TYPES:
            metadata_count+=1
        elif kind==TRACE_BEGIN:
            if start_seen or not version_seen or not full_vram_seen or not reset_seen:
                raise ValueError("TraceBegin without complete native GPU snapshot")
            # Require one E1..E6 restore series, in hardware order.
            if len(bootstrap)!=6 or any(
                    word>>24 != 0xe1+i for i,word in enumerate(bootstrap)):
                raise ValueError("missing ordered GP0(E1..E6) bootstrap state")
            start_seen=True
        elif not start_seen:
            if kind==GP1:
                if not reset_seen:
                    if tuple(words)!=(0,):
                        raise ValueError("native preamble must start GPU GP1 reset")
                    reset_seen=True
                else:
                    for word in words:
                        cmd=word>>24
                        if cmd in (3,4,5,8):
                            if cmd in pretrace_gp1_controls:
                                raise ValueError("ambiguous duplicate native pretrace GP1 control")
                            pretrace_gp1_controls[cmd]=word
            elif kind==GP0:
                if not reset_seen:
                    raise ValueError("native GPU initialization lacks reset")
                if not full_vram_seen:
                    if (len(words)!=FULL_VRAM_A0_WORDS or
                            words[0]!=0xa0000000 or
                            words[1]!=0 or words[2]!=0x02000400):
                        raise ValueError("native preamble lacks full 1024x512 A0 snapshot")
                    initial_vram=struct.pack("<%dI"%(len(words)-3),*words[3:])
                    if len(initial_vram)!=VRAM_BYTES:
                        raise ValueError("incomplete native VRAM snapshot")
                    full_vram_seen=True
                else:
                    bootstrap.extend(words)
            else:
                raise ValueError("unsupported native GPU initialization record")
        elif kind==VSYNC:
            frame_count+=1
            if not vsync_seen:
                vsync_seen=True
        elif not vsync_seen:
            if kind==GP0:
                live.extend(words)
                live_gp0_records+=1
            elif kind==GP1:
                for word in words:
                    cmd=word>>24
                    # Strictly idempotent: only display enable, DMA direction,
                    # VRAM display origin, and display mode, if captured with
                    # an identical full GP1 word in the native preamble.
                    # GP1 reset, IRQ ack, FIFO reset and GPU info are NEVER
                    # treated as harmless, even when their words repeat.
                    if (cmd not in (3,4,5,8) or
                            pretrace_gp1_controls.get(cmd)!=word):
                        raise ValueError("unsupported live GP1 state change or side effect")
                    idempotent_live_gp1_words+=1
            else:
                raise ValueError("unsupported live GP1/readback/metadata record")
        # Following the FIRST native frame, additional typed records
        # are structurally parsed but NOT reused with the stale initial VRAM.
    if not start_seen or not vsync_seen or not live or initial_vram is None:
        raise ValueError("native GPU capture missing completed first live frame")
    if len(live)*4>4*1024*1024:
        raise ValueError("first live GP0 frame too large for Stage446 adapter")
    all_words=bootstrap+live
    # Fail-closed on any unsupported GPU commands and malformed packet cuts.
    source=struct.pack("<%dI"%len(all_words),*all_words)
    packets, counts=packetize_owner_raw_words(source)
    if len(packets)<7:
        raise ValueError("native live frame lacks complete modelable packets")
    return {
        "initial_vram":initial_vram,
        "modeled_gp0_raw":source,
        "bootstrap_command_count":len(bootstrap),
        "actual_live_gp0_record_count":live_gp0_records,
        "live_gp0_word_count":len(live),
        "recorded_vsync_count":frame_count,
        "native_metadata_record_count":metadata_count,
        "idempotent_live_gp1_control_word_count":idempotent_live_gp1_words,
        "modeled_packet_counts":counts,
    }


def import_private_native_gpudump(native_path, output_vram_path,
                                   output_jsonl_path, *, frame=0):
    """Private no-clobber import of FIRST native frame and its initial VRAM."""
    if type(frame) is not int or frame<0:
        raise ValueError("frame must be a nonnegative integer")
    native_path, pre, out=map(Path,(native_path,output_vram_path,output_jsonl_path))
    if (native_path.is_symlink() or pre.is_symlink() or out.is_symlink()
            or not native_path.is_file() or
            pre.parent!=out.parent or not pre.parent.is_dir()
            or pre==out or pre.exists() or out.exists()
            or not 20<=native_path.stat().st_size<=MAX_DUMP_BYTES):
        raise ValueError("unsafe native GPU dump input or output paths")
    source=native_path.read_bytes()
    if len(source)>MAX_DUMP_BYTES:
        raise ValueError("native GPU dump changed length during read")
    data=select_first_native_gp0_frame(read_native_gpu_dump(source))
    with tempfile.TemporaryDirectory(
            prefix=".wa1-private-native-gpudump-",dir=pre.parent) as folder:
        tmp=Path(folder)
        temporary_vram=tmp/"vram.u16le.bin"
        temporary_raw=tmp/"gp0.raw.u32le"
        temporary_jsonl=tmp/"modeled-first-frame.jsonl"
        temporary_vram.write_bytes(data["initial_vram"])
        temporary_raw.write_bytes(data["modeled_gp0_raw"])
        os.chmod(temporary_vram,0o600)
        os.chmod(temporary_raw,0o600)
        packaged=package_private_gp0_raw_capture(
            temporary_raw,temporary_vram,temporary_jsonl,frame=frame)
        linked=[]
        try:
            for input_file, destination in (
                (temporary_vram,pre),(temporary_jsonl,out)):
                os.link(input_file,destination)
                linked.append(destination)
        except BaseException:
            for item in reversed(linked):
                item.unlink()
            raise
    return {
        "schema":1,
        "kind":"WA1_PRIVATE_PCSX_NATIVE_GPUDUMP_FIRST_FRAME_IMPORT",
        "upstream_source_revision":"de4a33e9a69abec4f567ae33567537f867dc2bba",
        "native_dump_sha256":hashlib.sha256(source).hexdigest(),
        "preframe_vram_sha256":packaged["initial_vram_sha256"],
        "modeled_trace_sha256":packaged["packaged_trace_sha256"],
        "bootstrap_state_gp0_word_count":data["bootstrap_command_count"],
        "live_frame_gp0_word_count":data["live_gp0_word_count"],
        "live_frame_gp0_record_count":data["actual_live_gp0_record_count"],
        "first_frame_model_packet_count":packaged["packet_count"],
        "native_total_completed_vsync_count":data["recorded_vsync_count"],
        "native_live_idempotent_gp1_word_count":data["idempotent_live_gp1_control_word_count"],
        "native_live_gp1_control_state_changes_rejected":True,
        "only_first_native_frame_selected":True,
        "bootstrap_state_is_pre_trace_restore_not_live_gameplay":True,
        "gpu_gp1_and_readback_unmodeled_live_events_rejected":(
            data["idempotent_live_gp1_control_word_count"]==0),
        "idempotent_native_gp1_commands_are_preamble_equivalent_only":True,
        "native_emulator_binary_version_not_attested_by_file_header":True,
        "original_game_disc_and_map_not_independently_authenticated":True,
        "all_native_game_data_and_hashes_remain_owner_private":True,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_native_gpu_dump")
    parser.add_argument("private_output_initial_vram")
    parser.add_argument("private_output_ordered_gp0_jsonl")
    parser.add_argument("--frame",type=int,default=0)
    args=parser.parse_args()
    print(json.dumps(import_private_native_gpudump(
        args.owner_private_native_gpu_dump,
        args.private_output_initial_vram,
        args.private_output_ordered_gp0_jsonl,
        frame=args.frame),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
