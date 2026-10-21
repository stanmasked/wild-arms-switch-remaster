#!/usr/bin/env python3
"""PRIVATE PS1 GP0 packet/Surf Village CLUT-coordinate correlation.

A matching CLUT coordinate and post-frame VRAM row is evidence from one
captured memory snapshot, not proof of pixels sampled at draw time.
The packet boundaries, chronology and frame identity must be supplied
by a trusted emulator; no original game data enters public CI.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit_surf_palette_rows import read_private_candidates
from audit_surf_vram_palette_occurrences import VRAM_BYTES, _row_filter

TRACE_KIND = "WA1_PRIVATE_PS1_GP0_PACKET_TRACE"
MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_PACKETS = 100_000
VRAM_WIDTH_WORDS = 1024
ROW_BYTES = 32


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def read_private_packet_trace(path, expected_vram_sha256):
    """Strict JSONL: first line header; remaining lines complete GP0 packets."""
    path = Path(path)
    if not 0 < path.stat().st_size <= MAX_TRACE_BYTES:
        raise ValueError("trace is empty or too large")
    with path.open("r", encoding="utf-8") as source:
        header = json.loads(source.readline(), object_pairs_hook=_unique_object)
        if not isinstance(header, dict) or set(header) != {
                "kind", "schema", "vram_sha256", "frame", "capture_phase"}:
            raise ValueError("invalid GP0 capture header")
        if (header["kind"] != TRACE_KIND or type(header["schema"]) is not int or
                header["schema"] != 1 or type(header["frame"]) is not int or
                header["frame"] < 0 or
                header["capture_phase"] != "post_packet_frame" or
                header["vram_sha256"] != expected_vram_sha256):
            raise ValueError("GP0 trace not linked to supplied VRAM snapshot")
        packets = []
        for number, line in enumerate(source, start=2):
            if number > MAX_PACKETS + 1:
                raise ValueError("too many GP0 packets")
            record = json.loads(line, object_pairs_hook=_unique_object)
            if not isinstance(record, dict) or set(record) != {"frame", "words"}:
                raise ValueError("invalid GP0 packet record")
            if type(record["frame"]) is not int or record["frame"] != header["frame"]:
                raise ValueError("packet frame differs from VRAM frame")
            words = record["words"]
            if (not isinstance(words, list) or not 1 <= len(words) <= 32 or
                    any(type(w) is not int or not 0 <= w <= 0xffffffff
                        for w in words)):
                raise ValueError("GP0 packet must have 1..32 unsigned words")
            packets.append(words)
    return header, packets


def decode_packet(words, draw_mode):
    """Decode known complete GP0 packets; unknown types invalidate E1 state."""
    if not isinstance(words, list) or not 1 <= len(words) <= 32 or any(
            type(w) is not int or not 0 <= w <= 0xffffffff for w in words):
        raise ValueError("invalid GP0 packet words")
    opcode = words[0] >> 24
    if opcode == 0xe1:
        if len(words) != 1:
            raise ValueError("GP0 E1 draw-mode command must have one word")
        return "SET_DRAW_MODE", words[0] & 0xffff, None
    if opcode in (0, 1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6):
        if len(words) != 1:
            raise ValueError("GP0 state/NOP command must have one word")
        return "NON_TEXTURE_STATE", draw_mode, None
    if 0x20 <= opcode <= 0x3f:
        gouraud = bool(opcode & 0x10)
        textured = bool(opcode & 4)
        vertices = 4 if opcode & 8 else 3
        expected = 1 + vertices * (1 + int(textured) + int(gouraud)) - int(gouraud)
        if len(words) != expected:
            raise ValueError("incomplete/overlong polygon packet")
        if not textured:
            return "UNTEXTURED_POLYGON", draw_mode, None
        first_uv = words[2]
        second_uv = words[4 + int(gouraud)]
        return "TEXTURED", draw_mode, {
            "primitive": "textured_polygon", "clut": first_uv >> 16,
            "tpage": second_uv >> 16,
            "u": first_uv & 0xff, "v": (first_uv >> 8) & 0xff}
    if 0x60 <= opcode <= 0x7f:
        textured = bool(opcode & 4)
        variable = ((opcode >> 3) & 3) == 0
        expected = 2 + int(textured) + int(variable)
        if len(words) != expected:
            raise ValueError("incomplete/overlong rectangle packet")
        if not textured:
            return "UNTEXTURED_RECTANGLE", draw_mode, None
        if draw_mode is None:
            return "RECTANGLE_WITHOUT_TPAGE", draw_mode, None
        return "TEXTURED", draw_mode, {
            "primitive": "textured_rectangle", "clut": words[2] >> 16,
            "tpage": draw_mode,
            "u": words[2] & 0xff, "v": (words[2] >> 8) & 0xff}
    return "UNSUPPORTED_PACKET", None, None


def analyze_gp0_packets(banks, vram, packets, *, frame, max_events=10000,
                        minimum_distinct_nonzero=3):
    """Match referenced CLUT coordinates to candidate *current* memory rows."""
    if len(vram) != VRAM_BYTES:
        raise ValueError("raw PS1 VRAM size mismatch")
    if (type(frame) is not int or frame < 0 or type(max_events) is not int or
            not 1 <= max_events <= 100_000 or
            type(minimum_distinct_nonzero) is not int or
            not 1 <= minimum_distinct_nonzero <= 16):
        raise ValueError("invalid analysis parameters")
    candidates = {}
    for bank_index, bank in enumerate(banks):
        if not isinstance(bank, bytes) or len(bank) != 512:
            raise ValueError("candidate palette bank must be 512 bytes")
        for row_index in range(16):
            row = bank[row_index*ROW_BYTES:(row_index+1)*ROW_BYTES]
            if _row_filter(row, minimum_distinct_nonzero) is None:
                candidates.setdefault(row, []).append({
                    "candidate_bank_index": bank_index,
                    "candidate_row_index": row_index})
    counters = Counter()
    evidence = []
    mode = None
    for packet_index, words in enumerate(packets):
        kind, mode, info = decode_packet(words, mode)
        counters[kind] += 1
        if kind != "TEXTURED":
            continue
        tpage = info["tpage"]
        if (tpage >> 7) & 3:
            counters["TEXTURED_NOT_4BPP"] += 1
            continue
        clut = info["clut"]
        if clut & 0x8000:
            counters["CLUT_RESERVED_BIT15"] += 1
            continue
        x = (clut & 0x3f)*16
        y = (clut >> 6) & 0x1ff
        if not (0 <= x <= 1008 and 0 <= y <= 511):
            counters["CLUT_OUTSIDE_1MB_VRAM"] += 1
            continue
        offset = (y*VRAM_WIDTH_WORDS+x)*2
        row = vram[offset:offset+ROW_BYTES]
        matches = candidates.get(row, [])
        counters["4BPP_CLUT_COORDINATE_REFERENCES"] += 1
        if matches:
            counters["4BPP_CLUT_REFERENCES_MATCHING_CANDIDATE"] += 1
        if len(evidence) >= max_events:
            counters["evidence_rows_not_emitted_due_to_limit"] += 1
            continue
        evidence.append({
            "packet_index": packet_index, "frame": frame,
            "opcode_hex": f"{words[0] >> 24:02x}",
            "primitive": info["primitive"],
            "clut_x_words": x, "clut_y": y,
            "texture_page_x_words": (tpage & 15)*64,
            "texture_page_y": ((tpage >> 4) & 1)*256,
            "first_u": info["u"], "first_v": info["v"],
            "vram_row_sha256": hashlib.sha256(row).hexdigest(),
            "candidate_bank_row_references": matches,
            "exact_current_snapshot_row_match": bool(matches)})
    return {
        "packet_count": len(packets),
        "counts": dict(sorted(counters.items())),
        "evidence": evidence,
        "candidate_unique_eligible_rows": len(candidates),
        "candidate_row_reference_count": sum(len(x) for x in candidates.values())}


def audit_private_gp0_clut(cdstg, vram_path, trace_path, *, map_index=2,
                           max_events=10000, **geometry):
    vram_path = Path(vram_path)
    if vram_path.stat().st_size != VRAM_BYTES:
        raise ValueError("VRAM must be exactly 1024x512 u16 little-endian")
    vram = vram_path.read_bytes()
    if len(vram) != VRAM_BYTES:
        raise ValueError("VRAM size changed during read")
    vram_sha = hashlib.sha256(vram).hexdigest()
    header, packets = read_private_packet_trace(trace_path, vram_sha)
    private = read_private_candidates(cdstg, map_index=map_index, **geometry)
    result = analyze_gp0_packets(private["candidate_banks"], vram, packets,
                                 frame=header["frame"], max_events=max_events)
    return {
        "schema": 1, "kind": "WA1_PRIVATE_SURF_GP0_CLUT_COORDINATE_EVIDENCE",
        "map_index": private["map_index"],
        "vram_sha256": vram_sha,
        "trace_sha256": hashlib.sha256(Path(trace_path).read_bytes()).hexdigest(),
        "capture_frame": header["frame"], "capture_phase": header["capture_phase"],
        "candidate_bank_count": len(private["candidate_banks"]),
        "bounded_lzss_stream_count": len(private["verified_streams"]),
        **result,
        "interpretation": {
            "trace_capture_provenance_not_independently_authenticated": True,
            "same_frame_vram_may_have_changed_since_draw_command": True,
            "match_is_gp0_coordinate_plus_post_frame_vram_bytes_only": True,
            "bank_to_stream_assignment_unverified": True,
            "no_original_scene_or_framebuffer_comparison": True,
            "no_original_palette_words_pixel_bytes_or_gp0_packet_words_exported": True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_cdstg", type=Path)
    parser.add_argument("private_vram", type=Path)
    parser.add_argument("private_gp0_jsonl", type=Path)
    parser.add_argument("--map-index", type=int, default=2)
    parser.add_argument("--max-events", type=int, default=10000)
    args = parser.parse_args()
    print(json.dumps(audit_private_gp0_clut(
        args.private_cdstg, args.private_vram, args.private_gp0_jsonl,
        map_index=args.map_index, max_events=args.max_events),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
