"""Original-game-free regression tests for Stage428 GP0/Surf CLUT evidence."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_surf_gp0_clut_references import (  # noqa: E402
    VRAM_BYTES, TRACE_KIND, analyze_gp0_packets,
    audit_private_gp0_clut, decode_packet, read_private_packet_trace)


def clut(x=32, y=19):
    return (y << 6) | (x // 16)


def polygon(*, opcode=0x24, page=0, palette=None):
    if palette is None:
        palette = clut()
    gouraud = bool(opcode & 0x10)
    vertices = 4 if opcode & 8 else 3
    words = [opcode << 24]
    for index in range(vertices):
        if gouraud and index:
            words.append(0x222222)
        words.append((200 + index) << 16 | 100 + index)
        words.append(((palette if index == 0 else page if index == 1 else 0)
                     << 16) | (27 << 8) | 12)
    return words


def rectangle(opcode=0x64):
    words = [opcode << 24, 0x00040003, (clut() << 16) | 0x140a]
    if not opcode & 0x18:
        words.append(0x00200020)
    return words


COLORS = struct.pack("<16H", 0, 31, 0x3e0, 0x7c00, *([0x7fff] * 12))
BANK = COLORS + bytes(512 - 32)


def memory(*, row=COLORS):
    data = bytearray(VRAM_BYTES)
    data[(19*1024 + 32)*2:(19*1024 + 32)*2+32] = row
    return bytes(data)


class Gp0ClutTests(unittest.TestCase):
    def test_flat_textured_triangle(self):
        kind, mode, info = decode_packet(polygon(), None)
        self.assertEqual((kind, mode), ("TEXTURED", None))
        self.assertEqual((info["clut"],info["tpage"],info["u"],info["v"]),
                         (clut(), 0, 12, 27))

    def test_gouraud_quad_offsets(self):
        words = polygon(opcode=0x3c,page=0x8f)
        self.assertEqual(len(words), 12)
        self.assertEqual(decode_packet(words,None)[2]["tpage"],0x8f)

    def test_flat_quad_and_gouraud_triangle_lengths(self):
        self.assertEqual(len(polygon(opcode=0x2c)),9)
        self.assertEqual(len(polygon(opcode=0x34)),9)
        self.assertEqual(decode_packet(polygon(opcode=0x34),None)[0],"TEXTURED")

    def test_polygon_page_is_in_packet(self):
        report = analyze_gp0_packets([BANK], memory(), [[0xe1000080],
                                          polygon(page=0)], frame=2)
        self.assertEqual(report["counts"]["4BPP_CLUT_REFERENCES_MATCHING_CANDIDATE"],1)

    def test_rectangle_e1_draw_mode(self):
        packets = [[0xe1000000],rectangle(),rectangle(0x74),rectangle(0x7c)]
        report=analyze_gp0_packets([BANK],memory(),packets,frame=2)
        self.assertEqual(report["counts"]["4BPP_CLUT_REFERENCES_MATCHING_CANDIDATE"],3)

    def test_rectangle_without_mode(self):
        report=analyze_gp0_packets([BANK],memory(),[rectangle()],frame=2)
        self.assertEqual(report["counts"]["RECTANGLE_WITHOUT_TPAGE"],1)

    def test_unknown_command_invalidates_mode(self):
        report=analyze_gp0_packets([BANK],memory(),
                    [[0xe1000000],[0xa0000000],rectangle()],frame=2)
        self.assertEqual(report["counts"]["RECTANGLE_WITHOUT_TPAGE"],1)

    def test_8bit_15bit_not_4bit(self):
        report=analyze_gp0_packets([BANK],memory(),
                    [polygon(page=0x80),polygon(page=0x100)],frame=2)
        self.assertEqual(report["counts"]["TEXTURED_NOT_4BPP"],2)

    def test_bit15_exact_row_match(self):
        changed=bytearray(COLORS)
        struct.pack_into("<H",changed,2,0x801f)
        report=analyze_gp0_packets([BANK],memory(row=changed),[polygon()],frame=2)
        self.assertFalse(report["evidence"][0]["exact_current_snapshot_row_match"])

    def test_duplicate_bank_reference_is_ambiguous(self):
        report=analyze_gp0_packets([BANK,BANK],memory(),[polygon()],frame=2)
        self.assertEqual(len(report["evidence"][0]["candidate_bank_row_references"]),2)

    def test_empty_rows_excluded(self):
        report=analyze_gp0_packets([bytes(512)],bytes(VRAM_BYTES),
                                   [polygon()],frame=2)
        self.assertFalse(report["evidence"][0]["exact_current_snapshot_row_match"])

    def test_bad_packet_lengths(self):
        for packet in ([0xe1000000,0],polygon()[:-1],rectangle()[:-1]):
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                decode_packet(packet,None)

    def test_limited_evidence_keeps_counts(self):
        report=analyze_gp0_packets([BANK],memory(),[polygon()]*3,
                                   frame=2,max_events=1)
        self.assertEqual(report["counts"]["4BPP_CLUT_COORDINATE_REFERENCES"],3)
        self.assertEqual(report["counts"]["evidence_rows_not_emitted_due_to_limit"],2)

    def test_invalid_vram_or_palette_bank(self):
        with self.assertRaises(ValueError):
            analyze_gp0_packets([BANK],bytes(20),[polygon()],frame=1)
        with self.assertRaises(ValueError):
            analyze_gp0_packets([bytes(511)],memory(),[polygon()],frame=1)

    def test_trace_sha_and_frame_pinning(self):
        digest=hashlib.sha256(memory()).hexdigest()
        header={"kind":TRACE_KIND,"schema":1,"vram_sha256":digest,
                "frame":55,"capture_phase":"post_packet_frame"}
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"trace.jsonl"
            file.write_text(json.dumps(header)+"\n"+json.dumps({
                "frame":55,"words":polygon()})+"\n",encoding="utf8")
            h,packets=read_private_packet_trace(file,digest)
            self.assertEqual((h["frame"],len(packets)),(55,1))
            with self.assertRaises(ValueError):
                read_private_packet_trace(file,"0"*64)
            file.write_text(json.dumps(header)+"\n"+json.dumps({
                "frame":56,"words":polygon()})+"\n")
            with self.assertRaises(ValueError):
                read_private_packet_trace(file,digest)

    def test_duplicate_json_key_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"trace.jsonl"
            file.write_text('{"schema":1,"schema":1}\n')
            with self.assertRaises(ValueError):
                read_private_packet_trace(file,"0"*64)

    def test_no_raw_words_or_color_values_in_evidence(self):
        report=analyze_gp0_packets([BANK],memory(),[polygon()],frame=2)
        encoded=json.dumps(report)
        self.assertNotIn('"words"',encoded)
        self.assertNotIn('"palette_words"',encoded)
        self.assertEqual(len(report["evidence"][0]["vram_row_sha256"]),64)

    def test_private_entrypoint_synthetic_dependencies(self):
        raw=memory()
        digest=hashlib.sha256(raw).hexdigest()
        header={"kind":TRACE_KIND,"schema":1,"vram_sha256":digest,
                "frame":2,"capture_phase":"post_packet_frame"}
        with tempfile.TemporaryDirectory() as temp:
            vr=Path(temp)/"vram.bin"
            tr=Path(temp)/"trace.jsonl"
            vr.write_bytes(raw)
            tr.write_text(json.dumps(header)+"\n"+json.dumps({
                "frame":2,"words":polygon()})+"\n")
            with patch("audit_surf_gp0_clut_references.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[]}):
                report=audit_private_gp0_clut("/not/a/disc.bin",vr,tr)
            self.assertEqual(report["counts"][
                "4BPP_CLUT_REFERENCES_MATCHING_CANDIDATE"],1)
            self.assertTrue(report["interpretation"][
                "same_frame_vram_may_have_changed_since_draw_command"])


if __name__ == "__main__":
    unittest.main()
