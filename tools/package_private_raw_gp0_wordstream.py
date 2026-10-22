#!/usr/bin/env python3
"""OWNER-PRIVATE packetizer for a raw little-endian GP0 *word* stream.

This is an adapter for an INDEPENDENTLY INSTRUMENTED emulator/source.
The PCSX-Redux GPU Logger GUI is useful for visual inspection but no
documented raw-word export has been verified. This adapter DOES NOT
collect, attest, or automatically extract anything from the emulator.

Only the strict Stage437–445 subset is accepted. An unsupported command,
truncated A0 image, malformed rectangle or invalid execution order
fails closed. No ROM, VRAM, raw GP0 words or private report in CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile

from audit_private_gp0_upload_timeline import (
    TRACE_KIND, MAX_PACKETS, MAX_PACKET_WORDS, VRAM_BYTES,
    read_private_gp0_timeline,
)
from audit_surf_gp0_clut_references import decode_packet

MAX_RAW_BYTES = 4 * 1024 * 1024
MAX_EMITTED_BYTES = 64 * 1024 * 1024


def packetize_owner_raw_words(source):
    """Split contiguous raw 32-bit words without treating A0 pixels as opcodes."""
    if type(source) is not bytes or len(source) == 0 or len(source) > MAX_RAW_BYTES:
        raise ValueError("raw GP0 wordstream empty, excessive or non-bytes")
    if len(source) % 4:
        raise ValueError("incomplete final 32-bit GP0 word")
    words = struct.unpack("<%dI" % (len(source)//4), source)
    pos = 0
    packets = []
    draw_mode = None
    e6_explicit_disabled = False
    counts = {}
    while pos < len(words):
        if len(packets) >= MAX_PACKETS:
            raise ValueError("too many GP0 packets in private frame")
        opcode = words[pos] >> 24
        if opcode == 0xa0:
            if not e6_explicit_disabled:
                raise ValueError("A0 transfer without explicit GP0(E6) mask disabled")
            if len(words) - pos < 3:
                raise ValueError("truncated GP0 A0 header")
            x, y = words[pos+1] & 0xffff, words[pos+1] >> 16
            width, height = words[pos+2] & 0xffff, words[pos+2] >> 16
            if (not 1 <= width <= 1024 or not 1 <= height <= 512
                    or x+width > 1024 or y+height > 512):
                raise ValueError("unsupported GP0 A0 bounds or wrapping")
            length = 3 + (width*height + 1)//2
            if length > MAX_PACKET_WORDS:
                raise ValueError("GP0 A0 exceeds Stage437 supported word limit")
        elif opcode == 0x80:
            if not e6_explicit_disabled:
                raise ValueError("80h copy without explicit GP0(E6) mask disabled")
            length = 4
        elif 0x20 <= opcode <= 0x3f:
            gouraud = bool(opcode & 0x10)
            textured = bool(opcode & 0x04)
            vertices = 4 if opcode & 0x08 else 3
            length = 1 + vertices*(1+int(textured)+int(gouraud)) - int(gouraud)
        elif 0x60 <= opcode <= 0x7f:
            textured = bool(opcode & 0x04)
            variable = ((opcode >> 3) & 3) == 0
            length = 2 + int(textured) + int(variable)
        elif opcode in (0x00,0x01,0xe1,0xe2,0xe3,0xe4,0xe5,0xe6):
            length = 1
        else:
            raise ValueError("unsupported GP0 opcode 0x%02x at word %d" %
                             (opcode, pos))
        if len(words)-pos < length:
            raise ValueError("incomplete final GP0 packet or A0 pixel payload")
        if length > MAX_PACKET_WORDS:
            raise ValueError("packet too large for Stage437 validator")
        packet = list(words[pos:pos+length])
        if opcode == 0xe6:
            if packet[0] != 0xe6000000:
                raise ValueError("GPU transfer mask state not explicitly disabled")
            e6_explicit_disabled = True
        elif opcode == 0xe2 and packet[0] & 0x00f00000:
            raise ValueError("GP0(E2) texture-window reserved bits set")
        elif opcode == 0x80:
            sx, sy = packet[1] & 0xffff, packet[1] >> 16
            dx, dy = packet[2] & 0xffff, packet[2] >> 16
            width, height = packet[3] & 0xffff, packet[3] >> 16
            if (not 1 <= width <= 1024 or not 1 <= height <= 512
                    or sx+width > 1024 or dx+width > 1024
                    or sy+height > 512 or dy+height > 512):
                raise ValueError("unsupported GP0(80) VRAM source/destination")
            if not (sx+width <= dx or dx+width <= sx
                    or sy+height <= dy or dy+height <= sy):
                raise ValueError("overlapping GP0(80) copy not supported")
        elif opcode not in (0xa0,):
            kind, draw_mode, _ = decode_packet(packet, draw_mode)
            if kind == "UNSUPPORTED_PACKET":
                raise ValueError("GP0 command unsupported by modeled renderer")
        label = "A0_UPLOAD" if opcode == 0xa0 else (
            "80_COPY" if opcode == 0x80 else "OTHER_SUPPORTED")
        counts[label] = counts.get(label, 0) + 1
        packets.append(packet)
        pos += length
    return packets, counts


def package_private_gp0_raw_capture(raw_wordstream_path, initial_vram_path,
                                     output_jsonl_path, *, frame,
                                     expected_raw_sha256=None):
    """Build Stage437-compatible private JSONL, no-clobber, mode 0600.

    A finite wordstream ending at a packet boundary does NOT by itself
    certify that this is a complete frame or genuine emulator trace.
    """
    if type(frame) is not int or frame < 0:
        raise ValueError("frame must be a nonnegative integer")
    raw_path, vram_path, destination = map(
        Path,(raw_wordstream_path,initial_vram_path,output_jsonl_path))
    if raw_path.is_symlink() or vram_path.is_symlink() or destination.is_symlink():
        raise ValueError("private trace inputs/destination cannot be symlinks")
    if not (raw_path.is_file() and vram_path.is_file() and destination.parent.is_dir()
            and 0 < raw_path.stat().st_size <= MAX_RAW_BYTES
            and vram_path.stat().st_size == VRAM_BYTES):
        raise ValueError("invalid private raw GP0 or initial VRAM geometry")
    if destination.exists():
        raise FileExistsError("private GP0 JSONL destination already exists")
    if expected_raw_sha256 is not None and (
            type(expected_raw_sha256) is not str or
            re.fullmatch(r"[0-9a-f]{64}",expected_raw_sha256) is None):
        raise ValueError("expected raw SHA-256 must be lowercase 64-hex")
    raw = raw_path.read_bytes()
    vram = vram_path.read_bytes()
    if len(raw) > MAX_RAW_BYTES or len(vram) != VRAM_BYTES:
        raise ValueError("private input sizes changed during read")
    raw_digest = hashlib.sha256(raw).hexdigest()
    if expected_raw_sha256 is not None and raw_digest != expected_raw_sha256:
        raise ValueError("raw GP0 SHA-256 disagrees with independently supplied value")
    packets, counts = packetize_owner_raw_words(raw)
    header = {
        "schema":1, "kind":TRACE_KIND, "frame":frame,
        "capture_phase":"before_first_packet",
        "initial_vram_sha256":hashlib.sha256(vram).hexdigest(),
    }
    lines = [json.dumps(header,sort_keys=True,separators=(",",":"))]
    lines += [json.dumps({"frame":frame,"words":packet},
                         separators=(",",":")) for packet in packets]
    output = ("\n".join(lines)+"\n").encode("utf-8")
    if len(output) > MAX_EMITTED_BYTES:
        raise ValueError("JSONL exceeds private Stage437 supported size")
    # Re-parse the complete generated JSONL before publishing; its
    # format is the strict Stage437 interface, not an invented schema.
    fd,temporary = tempfile.mkstemp(prefix=".private-gp0-stage446-",
                                     dir=destination.parent)
    temp=Path(temporary)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,0o600)
        from audit_private_gp0_upload_timeline import read_private_gp0_timeline
        got_header, got_packets, _ = read_private_gp0_timeline(
            temp,header["initial_vram_sha256"])
        if got_header != header or got_packets != packets:
            raise ValueError("generated owner-private trace failed revalidation")
        os.link(temp,destination)  # atomic no-overwrite on same filesystem
    finally:
        temp.unlink(missing_ok=True)
    return {
        "kind":"WA1_PRIVATE_GP0_RAW_WORDSTREAM_CONVERSION",
        "schema":1,
        "frame":frame,
        "raw_word_count":len(raw)//4,
        "packet_count":len(packets),
        "opcode_group_counts":counts,
        "raw_gp0_sha256":raw_digest,
        "initial_vram_sha256":header["initial_vram_sha256"],
        "packaged_trace_sha256":hashlib.sha256(output).hexdigest(),
        "raw_capture_is_original_emulator_trace_unverified":True,
        "full_frame_completeness_not_verified_by_packetization":True,
        "matching_hashes_are_consistency_not_emulator_attestation":True,
        "original_source_disc_scene_and_camera_not_authenticated":True,
        "all_trace_and_hash_metadata_owner_private":True,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_raw_gp0_u32le")
    parser.add_argument("private_prepacket_vram_u16le")
    parser.add_argument("private_output_jsonl")
    parser.add_argument("--frame",type=int,required=True)
    parser.add_argument("--expected-raw-sha256")
    args=parser.parse_args()
    print(json.dumps(package_private_gp0_raw_capture(
        args.private_raw_gp0_u32le,args.private_prepacket_vram_u16le,
        args.private_output_jsonl,frame=args.frame,
        expected_raw_sha256=args.expected_raw_sha256),sort_keys=True,indent=2))


if __name__=="__main__":
    main()
