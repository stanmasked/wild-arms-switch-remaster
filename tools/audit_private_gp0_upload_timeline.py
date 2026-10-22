#!/usr/bin/env python3
"""PRIVATE ordered GP0 upload/blit/4bpp CLUT timeline, without original assets.

Stage428 compared CLUT coordinates with POST-frame VRAM, which can be stale
relative to a draw. Stage437 models supported GP0(A0) CPU-to-VRAM and
GP0(80) VRAM-to-VRAM transfers in exact packet order from a PRE-trace
snapshot, and inspects palette rows immediately BEFORE supported draws.
Any unsupported GP0 command fails closed. Rendered framebuffer writes
and PS1 texture/CLUT cache behavior are not emulated or authenticated.
"""
import argparse
from array import array
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

from audit_surf_gp0_clut_references import decode_packet
from audit_private_gp0_texture_first_uv import probe_first_uv_4bpp
from audit_surf_palette_rows import read_private_candidates
from audit_surf_vram_palette_occurrences import _row_filter, VRAM_BYTES

TRACE_KIND = "WA1_PRIVATE_GP0_CPU_UPLOAD_DRAW_TIMELINE"
MAX_TRACE_BYTES = 64 * 1024 * 1024
MAX_PACKETS = 20_000
MAX_PACKET_WORDS = 131_075
MAX_EVIDENCE = 20_000
VRAM_WIDTH = 1024
VRAM_HEIGHT = 512
PALETTE_BYTES = 32


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate trace JSON key")
        result[key] = value
    return result


def _exact_hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def read_private_gp0_timeline(path, expected_initial_vram_sha256):
    """Accept complete packetized JSONL only, not arbitrary DMA fragments."""
    if not _exact_hash(expected_initial_vram_sha256):
        raise ValueError("invalid initial VRAM SHA-256")
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or
            not 0 < path.stat().st_size <= MAX_TRACE_BYTES):
        raise ValueError("invalid or excessive private GP0 timeline")
    with path.open("rb") as file:
        source = file.read(MAX_TRACE_BYTES + 1)
    if len(source) > MAX_TRACE_BYTES or not source.endswith(b"\n"):
        raise ValueError("incomplete or excessive GP0 JSONL stream")
    try:
        lines = source.decode("utf-8").splitlines()
        if not lines or len(lines) > MAX_PACKETS + 1:
            raise ValueError("invalid GP0 timeline packet count")
        header = json.loads(lines[0], object_pairs_hook=_unique_json)
        if (type(header) is not dict or set(header) != {
                "schema", "kind", "frame", "capture_phase", "initial_vram_sha256"}
                or type(header["schema"]) is not int or header["schema"] != 1
                or header["kind"] != TRACE_KIND
                or type(header["frame"]) is not int or header["frame"] < 0
                or header["capture_phase"] != "before_first_packet"
                or header["initial_vram_sha256"] != expected_initial_vram_sha256):
            raise ValueError("GP0 timeline header disagrees with private preframe VRAM")
        packets = []
        for line in lines[1:]:
            item = json.loads(line, object_pairs_hook=_unique_json)
            if (type(item) is not dict or set(item) != {"frame", "words"}
                    or type(item["frame"]) is not int
                    or item["frame"] != header["frame"] or
                    type(item["words"]) is not list or
                    not 1 <= len(item["words"]) <= MAX_PACKET_WORDS or
                    any(type(word) is not int or not 0 <= word <= 0xffffffff
                        for word in item["words"])):
                raise ValueError("GP0 timeline contains invalid complete packet")
            packets.append(item["words"])
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed GP0 timeline JSONL") from exc
    return header, packets, hashlib.sha256(source).hexdigest()


def _rect(word, size, *, field):
    """Conservative in-bounds rectangles; wrapped GPU copies are excluded."""
    if type(word) is not int or type(size) is not int:
        raise ValueError("invalid GP0 rectangle word")
    x, y = word & 0xffff, (word >> 16) & 0xffff
    width, height = size & 0xffff, (size >> 16) & 0xffff
    if (not 1 <= width <= VRAM_WIDTH or not 1 <= height <= VRAM_HEIGHT
            or x >= VRAM_WIDTH or y >= VRAM_HEIGHT
            or x + width > VRAM_WIDTH or y + height > VRAM_HEIGHT):
        raise ValueError("GP0 " + field + " rectangle wraps or exceeds VRAM")
    return x, y, width, height


def _build_candidates(banks, minimum_distinct_nonzero):
    if (type(minimum_distinct_nonzero) is not int
            or not 1 <= minimum_distinct_nonzero <= 16):
        raise ValueError("invalid palette distinct-color threshold")
    candidates = {}
    for bank_index, bank in enumerate(banks):
        if type(bank) is not bytes or len(bank) != 512:
            raise ValueError("candidate bank requires exact 512 bytes")
        for row_index in range(16):
            value = bank[row_index*PALETTE_BYTES:(row_index+1)*PALETTE_BYTES]
            if _row_filter(value, minimum_distinct_nonzero) is None:
                candidates.setdefault(value, []).append({
                    "candidate_bank_index": bank_index,
                    "candidate_row_index": row_index})
    return candidates


def replay_private_gp0_clut_timeline(initial_vram, packets, banks, *,
                                     frame=0, max_evidence=MAX_EVIDENCE,
                                     minimum_distinct_nonzero=3,
                                     observed_post_vram=None,
                                     require_post_match=False):
    """Replay only supported pixel-copy GP0 operations; conservatively score draws.

    Freshly written means all 16 CLUT halfwords were copied/uploaded AFTER
    the preceding draw packet. Because GPU drawing writes are not modeled,
    baseline-only and older uploaded rows cannot be certified stable after
    a draw; a fresh whole-row write at least restores its known contents.
    """
    if (type(initial_vram) is not bytes or len(initial_vram) != VRAM_BYTES
            or type(frame) is not int or frame < 0
            or type(max_evidence) is not int or not 1 <= max_evidence <= MAX_EVIDENCE):
        raise ValueError("invalid GP0 replay inputs")
    if type(require_post_match) is not bool:
        raise ValueError("require_post_match must be a boolean")
    if (observed_post_vram is not None and
            (type(observed_post_vram) is not bytes or
             len(observed_post_vram) != VRAM_BYTES)):
        raise ValueError("post-packet VRAM must be exactly 1048576 bytes")
    if require_post_match and observed_post_vram is None:
        raise ValueError("cannot require postframe match without a postframe VRAM")
    palette_rows = _build_candidates(banks, minimum_distinct_nonzero)
    vram = bytearray(initial_vram)
    # Each u16 pixel records the most recent *completed* draw epoch in which
    # it was explicitly rewritten by a modeled copy/upload. -1 = no proof.
    pixel_epoch = array("i", [-1]) * (VRAM_WIDTH*VRAM_HEIGHT)
    draw_epoch = 0
    draw_mode = None
    mask_mode = None  # GPU state at preframe snapshot is unknown.
    texture_window = None  # An initial GPU E2 register value is unknown.
    evidence = []
    counters = Counter()
    for index, packet in enumerate(packets):
        if (type(packet) is not list or not 1 <= len(packet) <= MAX_PACKET_WORDS or
                any(type(x) is not int or not 0 <= x <= 0xffffffff for x in packet)):
            raise ValueError("invalid GP0 packet sequence element")
        opcode = packet[0] >> 24
        if opcode == 0xe2:
            # Texture-window control GP0(E2) has four 5-bit fields.
            # Unknown/nonzero settings forbid first-UV sampling until
            # a subsequent explicit E2 zero clears the ambiguity.
            if len(packet) != 1 or packet[0] & 0x00f00000:
                raise ValueError("invalid or reserved GP0 E2 texture-window bits")
            texture_window = packet[0] & 0x000fffff
            counters["E2_TEXTURE_WINDOW_EXPLICIT"] += 1
            continue
        if opcode == 0xe6:
            # GP0(E6) changes bit15 masking for CPU/GPU copies too.
            # Modeling those cases would require true GPU mask semantics.
            if len(packet) != 1 or packet[0] & 3:
                raise ValueError("unsupported GP0 E6 VRAM write-mask mode")
            mask_mode = 0
            counters["E6_NO_VRAM_MASK"] += 1
            continue
        if opcode in (0xa0, 0x80) and mask_mode != 0:
            raise ValueError("GP0 transfers require prior explicit E6 masking-disabled state")
        if opcode == 0xa0:
            if len(packet) < 4:
                raise ValueError("truncated GP0 A0 CPU-to-VRAM packet")
            x, y, width, height = _rect(packet[1], packet[2], field="A0")
            pixels = width*height
            if len(packet) != 3 + (pixels+1)//2:
                raise ValueError("GP0 A0 does not contain exactly the expected image words")
            if pixels > VRAM_WIDTH*VRAM_HEIGHT:
                raise ValueError("excessive GP0 A0 image")
            # 32-bit GP0 data words are two little-endian u16 pixels each.
            # A trailing odd pixel leaves the final high halfword unused.
            payload = struct.pack("<%dI" % (len(packet)-3), *packet[3:])
            for j in range(pixels):
                dx, dy = x+(j % width), y+(j//width)
                address = dy*VRAM_WIDTH+dx
                vram[address*2:address*2+2] = payload[j*2:j*2+2]
                pixel_epoch[address] = draw_epoch
            counters["A0_CPU_TO_VRAM"] += 1
            continue
        if opcode == 0x80:
            if len(packet) != 4:
                raise ValueError("GP0 80 VRAM-to-VRAM packet must contain four words")
            sx, sy, width, height = _rect(packet[1], packet[3], field="80 source")
            dx, dy, dwidth, dheight = _rect(packet[2], packet[3], field="80 target")
            if (width, height) != (dwidth,dheight):
                raise ValueError("inconsistent GPU copy dimensions")
            if not (dx+width <= sx or sx+width <= dx or
                    dy+height <= sy or sy+height <= dy):
                raise ValueError("overlapping GPU VRAM copy is unsupported")
            snapshot = []
            for ry in range(height):
                start = (sy+ry)*VRAM_WIDTH+sx
                snapshot.append((bytes(vram[start*2:(start+width)*2]),
                                 pixel_epoch[start:start+width]))
            for ry, (data, states) in enumerate(snapshot):
                start = (dy+ry)*VRAM_WIDTH+dx
                vram[start*2:(start+width)*2] = data
                pixel_epoch[start:start+width] = states
            counters["80_VRAM_TO_VRAM"] += 1
            continue
        if len(packet) > 32:
            raise ValueError("unsupported oversized GP0 packet")
        kind, draw_mode, info = decode_packet(packet, draw_mode)
        if kind == "UNSUPPORTED_PACKET":
            raise ValueError("unknown GP0 packet may modify VRAM; replay fails closed")
        counters[kind] += 1
        is_draw = kind in (
            "TEXTURED", "UNTEXTURED_POLYGON", "UNTEXTURED_RECTANGLE",
            "RECTANGLE_WITHOUT_TPAGE")
        if kind == "TEXTURED":
            tpage = info["tpage"]
            if (tpage >> 7) & 3:
                counters["TEXTURED_NOT_4BPP"] += 1
            else:
                clut = info["clut"]
                if clut & 0x8000:
                    raise ValueError("reserved CLUT bit15 set")
                x, y = (clut & 0x3f)*16, (clut >> 6) & 0x1ff
                offset = (y*VRAM_WIDTH+x)*2
                row = bytes(vram[offset:offset+PALETTE_BYTES])
                start = y*VRAM_WIDTH+x
                fresh = all(pixel_epoch[i] == draw_epoch
                            for i in range(start,start+16))
                candidates = palette_rows.get(row, [])
                counters["4BPP_CLUT_DRAWS"] += 1
                if fresh:
                    counters["4BPP_CLUT_FULL_ROW_REWRITTEN_SINCE_LAST_DRAW"] += 1
                if candidates:
                    counters["4BPP_CLUT_MODELED_ROW_MATCHES_SOURCE"] += 1
                if len(evidence) < max_evidence:
                    texture_probe = probe_first_uv_4bpp(
                        vram, pixel_epoch, draw_epoch, info, texture_window)
                    counters["FIRST_UV_PROBE_" + texture_probe["status"]] += 1
                    evidence.append({
                        "first_uv_texture_probe": texture_probe,
                        "packet_index": index,
                        "frame": frame,
                        "primitive": info["primitive"],
                        "clut_x_words": x,
                        "clut_y": y,
                        "texture_page_x_words": (tpage & 15)*64,
                        "texture_page_y": ((tpage >> 4)&1)*256,
                        "row_sha256_before_draw": hashlib.sha256(row).hexdigest(),
                        "candidate_bank_row_references": candidates,
                        "modeled_pre_draw_row_matches_candidate": bool(candidates),
                        "all_16_words_explicitly_written_since_previous_draw": fresh,
                        "source_frame_initial_vram_or_copy_replay_unverified": True,
                        "actual_gpu_sampled_clut_not_observed": True,
                    })
                else:
                    counters["evidence_rows_truncated"] += 1
        if is_draw:
            # Drawing may modify any VRAM location. Without pixel-level GPU
            # rasterization its overlap with CLUT memory cannot be excluded.
            draw_epoch += 1
            counters["GPU_DRAW_PACKET_NOT_RASTERIZED"] += 1
    reconciliation = None
    if observed_post_vram is not None:
        # GP0 drawing is not rasterized. ONLY words explicitly rewritten
        # after the most recent draw have a known final value. With no
        # draws, all words retain modeled contents under the full-trace
        # premise, even if they were originally present in the baseline.
        if draw_epoch == 0:
            known_words = VRAM_WIDTH * VRAM_HEIGHT
            mismatches = sum(
                vram[index*2:index*2+2] != observed_post_vram[index*2:index*2+2]
                for index in range(known_words))
            comparison_scope = "ENTIRE_VRAM_NO_GPU_DRAW_PACKETS"
        else:
            known_words = 0
            mismatches = 0
            for index, epoch in enumerate(pixel_epoch):
                if epoch == draw_epoch:
                    known_words += 1
                    if (vram[index*2:index*2+2] !=
                            observed_post_vram[index*2:index*2+2]):
                        mismatches += 1
            comparison_scope = "EXPLICIT_TRANSFERS_AFTER_LAST_DRAW_ONLY"
        verdict = None if known_words == 0 else mismatches == 0
        reconciliation = {
            "scope": comparison_scope,
            "post_vram_sha256": hashlib.sha256(observed_post_vram).hexdigest(),
            "modeled_vram_sha256_untrusted_where_drawing_unmodeled":
                hashlib.sha256(vram).hexdigest(),
            "known_final_u16_word_count": known_words,
            "unknown_or_unmodeled_final_u16_word_count":
                VRAM_WIDTH * VRAM_HEIGHT - known_words,
            "mismatched_known_u16_word_count": mismatches,
            "all_comparable_words_match": verdict,
            "no_comparable_words_means_no_verdict": known_words == 0,
            "postframe_snapshot_timing_not_authenticated": True,
            "gpu_drawn_pixels_and_cache_effects_unmodeled": True,
            "no_raw_vram_words_or_pixel_values_exported": True,
        }
        if require_post_match and verdict is not True:
            raise ValueError(
                "postframe reconciliation has no known comparable words or mismatch")
    return {
        "schema": 1,
        "kind": "WA1_PRIVATE_SURF_GP0_UPLOAD_CLUT_TIMELINE",
        "frame": frame,
        "packet_count": len(packets),
        "counts": dict(sorted(counters.items())),
        "initial_vram_sha256": hashlib.sha256(initial_vram).hexdigest(),
        "candidate_eligible_distinct_rows": len(palette_rows),
        "candidate_bank_row_reference_count": sum(map(len,palette_rows.values())),
        "clut_draw_events": evidence,
        "postframe_reconciliation": reconciliation,
        "interpretation": {
            "gpu_a0_and_nonoverlapping_80_copy_replayed_in_order": True,
            "gpu_e6_masking_disabled_explicitly_required_for_transfers": True,
            "all_nonreplayed_gp0_commands_rejected_or_non_vram_state_or_draw": True,
            "gpu_framebuffer_drawing_not_rasterized": True,
            "pre_frame_snapshot_origin_not_independently_authenticated": True,
            "fresh_row_word_write_after_previous_draw_is_conditional_evidence_only": True,
            "actual_ps1_texture_and_clut_cache_semantics_unverified": True,
            "first_uv_does_not_establish_visible_framebuffer_sampling": True,
            "nonzero_or_unobserved_gpu_e2_texture_window_not_assumed_zero": True,
            "gp0_packet_trace_provenance_and_completeness_unverified": True,
            "no_final_post_frame_vram_equivalence_claim": True,
            "no_original_vram_words_palette_values_or_packets_in_report": True,
        },
    }


def audit_private_gp0_upload_timeline(cdstg, initial_vram_path, timeline_path,
                                       *, map_index=2, max_evidence=MAX_EVIDENCE,
                                       observed_post_vram_path=None,
                                       require_post_match=False):
    path = Path(initial_vram_path)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size != VRAM_BYTES):
        raise ValueError("initial VRAM must be an exact 1MiB private snapshot")
    initial = path.read_bytes()
    if len(initial) != VRAM_BYTES:
        raise ValueError("private VRAM changed length during read")
    digest = hashlib.sha256(initial).hexdigest()
    header, packets, trace_digest = read_private_gp0_timeline(timeline_path,digest)
    observed_post_vram = None
    if observed_post_vram_path is not None:
        post_path = Path(observed_post_vram_path)
        if (post_path.is_symlink() or not post_path.is_file()
                or post_path.stat().st_size != VRAM_BYTES):
            raise ValueError("post-packet private VRAM must be an exact 1MiB file")
        observed_post_vram = post_path.read_bytes()
        if len(observed_post_vram) != VRAM_BYTES:
            raise ValueError("post-packet private VRAM length changed during read")
    private = read_private_candidates(cdstg,map_index=map_index)
    report = replay_private_gp0_clut_timeline(
        initial,packets,private["candidate_banks"],
        frame=header["frame"],max_evidence=max_evidence,
        observed_post_vram=observed_post_vram,
        require_post_match=require_post_match)
    return {
        **report,
        "source_map_index": private["map_index"],
        "source_verified_lzss_stream_count": len(private["verified_streams"]),
        "private_trace_sha256": trace_digest,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cdstg",type=Path)
    ap.add_argument("private_initial_vram_u16le",type=Path)
    ap.add_argument("private_complete_gp0_timeline_jsonl",type=Path)
    ap.add_argument("--map-index",type=int,default=2)
    ap.add_argument("--max-evidence",type=int,default=MAX_EVIDENCE)
    ap.add_argument("--post-vram",type=Path,
                    help="Optional private 1 MiB VRAM AFTER ordered packets")
    ap.add_argument("--require-post-match",action="store_true",
                    help="Fail if no deterministically comparable words or any mismatch")
    args=ap.parse_args()
    print(json.dumps(audit_private_gp0_upload_timeline(
        args.private_cdstg,args.private_initial_vram_u16le,
        args.private_complete_gp0_timeline_jsonl,map_index=args.map_index,
        max_evidence=args.max_evidence,
        observed_post_vram_path=args.post_vram,
        require_post_match=args.require_post_match),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
