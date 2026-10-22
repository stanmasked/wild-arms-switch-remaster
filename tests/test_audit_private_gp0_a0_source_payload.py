"""Stage442: synthetic private decoded source to GP0 A0 transfer payload tests."""
from array import array
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_private_gp0_a0_source_payload import match_a0_source_payload
from audit_private_surf_gp0_stream_uv_link import prepare_private_stream_index
from audit_private_gp0_upload_timeline import (
    VRAM_BYTES, replay_private_gp0_clut_timeline, audit_private_gp0_upload_timeline)
from test_audit_private_gp0_upload_timeline import BANK, E6, a0, vram, write_trace

SOURCE=bytes((i*17 + (i//64)*31+5)%256 for i in range(192))


def stream(raw=SOURCE,index=6):
    return {"decoded":raw,"graphics_region_index":index}


def packet(raw=SOURCE, *, x=0, y=0, width=None, height=1):
    width=len(raw)//(2*height) if width is None else width
    return a0(raw,x=x,y=y,width=width,height=height)


def evaluate(raw=SOURCE,*,sources=None,**opts):
    index=prepare_private_stream_index(
        [stream()] if sources is None else sources)
    return match_a0_source_payload(index, packet(raw),**opts)


class Stage442GP0PayloadTests(unittest.TestCase):
    def test_three_exact_blocks_inside_a0_transfer(self):
        report=evaluate()
        self.assertEqual(report["matching_decoded_stream_run_count"],1)
        self.assertEqual(report["a0_effective_pixel_bytes"],192)
        sample=report["run_samples"][0]
        self.assertEqual(sample["source_offset_bytes"],0)
        self.assertEqual((sample["a0_destination_x_words"],sample["a0_destination_y"]),(0,0))
        self.assertEqual(sample["matched_contiguous_64byte_blocks"],3)
        self.assertEqual(sample["run_sha256"],hashlib.sha256(SOURCE).hexdigest())

    def test_a0_payload_even_when_not_written_to_final_vram(self):
        index=prepare_private_stream_index([stream()])
        p=packet()
        direct=match_a0_source_payload(index,p)
        self.assertEqual(direct["matching_decoded_stream_run_count"],1)
        self.assertTrue(direct["interpretation"][
            "a0_payload_not_proof_that_textured_draw_sampled_these_words"])

    def test_changed_byte_rejects_three_block_run(self):
        raw=bytearray(SOURCE)
        raw[77]^=1
        self.assertEqual(evaluate(bytes(raw))["matching_decoded_stream_run_count"],0)

    def test_128_byte_match_not_enough(self):
        raw=SOURCE[:128]+bytes(64)
        self.assertEqual(evaluate(raw)["matching_decoded_stream_run_count"],0)

    def test_unknown_source_does_not_match(self):
        report=evaluate(sources=[stream(bytes(192))])
        self.assertEqual(report["matching_decoded_stream_run_count"],0)

    def test_source_offset_nonzero_is_preserved(self):
        prefixed=bytes(range(64))+SOURCE
        report=evaluate(sources=[stream(prefixed)])
        self.assertEqual(report["run_samples"][0]["source_offset_bytes"],64)

    def test_repeat_source_ambiguity_not_called_unique(self):
        report=evaluate(sources=[stream(),stream(index=8)])
        self.assertEqual(report["matching_decoded_stream_run_count"],2)
        self.assertEqual({x["graphics_region_index"] for x in report["run_samples"]},
                         {6,8})

    def test_all_zero_repetitive_source_excluded(self):
        report=evaluate(bytes(192),sources=[stream(bytes(192))])
        self.assertEqual(report["matching_decoded_stream_run_count"],0)

    def test_unaligned_a0_destination_realigns_at_absolute_vram_grid(self):
        # Transfer x=1; 15 u16 words before a 192-byte source run.
        raw=bytes(30)+SOURCE
        p=packet(raw,x=1)
        index=prepare_private_stream_index([stream()])
        report=match_a0_source_payload(index,p)
        self.assertEqual(report["matching_decoded_stream_run_count"],1)
        self.assertEqual(report["run_samples"][0]["a0_destination_x_words"],16)
        self.assertEqual(report["run_samples"][0]["a0_row_offset_bytes"],30)

    def test_run_inside_middle_of_two_row_transfer(self):
        raw=bytes(192)+SOURCE
        p=packet(raw,x=32,y=20,width=96,height=2)
        report=match_a0_source_payload(prepare_private_stream_index([stream()]),p)
        self.assertEqual(report["matching_decoded_stream_run_count"],1)
        self.assertEqual(report["run_samples"][0]["a0_destination_y"],21)
        self.assertEqual(report["run_samples"][0]["a0_payload_row_index"],1)

    def test_does_not_cross_a0_transfer_row_boundary(self):
        # Source bytes split into two 96-byte A0 rows: no 192-byte run.
        raw=SOURCE
        p=packet(raw,width=48,height=2)
        report=match_a0_source_payload(prepare_private_stream_index([stream()]),p)
        self.assertEqual(report["matching_decoded_stream_run_count"],0)

    def test_edge_of_vram_accepted_if_contained(self):
        p=packet(SOURCE,x=928,y=511)
        result=match_a0_source_payload(prepare_private_stream_index([stream()]),p)
        self.assertEqual(result["matching_decoded_stream_run_count"],1)
        self.assertEqual(result["run_samples"][0]["a0_destination_x_words"],928)

    def test_out_of_bounds_a0_rejected(self):
        p=packet(SOURCE,x=929,y=511)
        with self.assertRaisesRegex(ValueError,"geometry"):
            match_a0_source_payload(prepare_private_stream_index([stream()]),p)

    def test_padding_of_odd_pixel_count_is_not_hashed(self):
        raw=b"\x01\x02\x03\x04\x05\x06"
        p=packet(raw)
        report=match_a0_source_payload(prepare_private_stream_index([stream()]),p)
        self.assertEqual(report["a0_effective_pixel_bytes"],6)
        self.assertEqual(report["a0_payload_sha256"],hashlib.sha256(raw).hexdigest())

    def test_rejects_wrong_packet_word_count_and_opcode(self):
        idx=prepare_private_stream_index([stream()])
        for p in (packet()[:-1],packet()+[0], [0x80000000,0,0,0],
                  [0xa0000000,0,0,0]):
            with self.subTest(length=len(p)),self.assertRaises(ValueError):
                match_a0_source_payload(idx,p)

    def test_sample_cap_preserves_full_counts(self):
        report=evaluate(sources=[stream(),stream(index=8)],
                        max_run_samples=1)
        self.assertEqual(report["matching_decoded_stream_run_count"],2)
        self.assertEqual(len(report["run_samples"]),1)
        self.assertTrue(report["sample_truncated"])

    def test_integration_counts_raw_a0_source_runs_and_packets(self):
        out=replay_private_gp0_clut_timeline(
            vram(),[E6,packet(),packet(SOURCE,x=96)],
            [BANK],source_streams=[stream()],frame=442)
        self.assertEqual(out["counts"]["A0_SOURCE_BYTE_RUN_MATCHES"],2)
        self.assertEqual(out["counts"]["A0_PACKETS_WITH_SOURCE_RUNS"],2)
        self.assertEqual(len(out["a0_source_payload_reports"]),2)
        self.assertEqual(out["a0_source_payload_reports"][1]["packet_index"],2)
        self.assertTrue(out["interpretation"][
            "a0_payload_matches_do_not_authenticate_gpu_upload_or_draw_use"])

    def test_draw_after_upload_does_not_become_visible_scene_proof(self):
        from test_audit_private_gp0_texture_first_uv import E2_ZERO,sample_polygon
        out=replay_private_gp0_clut_timeline(
            vram(),[E2_ZERO,E6,packet(),sample_polygon()],
            [BANK],source_streams=[stream()])
        self.assertEqual(out["counts"]["A0_SOURCE_BYTE_RUN_MATCHES"],1)
        self.assertTrue(out["a0_source_payload_reports"][0]["report"][
            "interpretation"]["clut_and_visible_map_geometry_unverified"])

    def test_capped_packet_reports_still_count_all_matches(self):
        out=replay_private_gp0_clut_timeline(
            vram(),[E6,packet(),packet(SOURCE,x=96),packet(SOURCE,x=192)],
            [BANK],source_streams=[stream()],max_evidence=1)
        self.assertEqual(out["counts"]["A0_SOURCE_BYTE_RUN_MATCHES"],3)
        self.assertEqual(out["counts"]["A0_SOURCE_PACKET_REPORTS_TRUNCATED"],2)
        self.assertEqual(len(out["a0_source_payload_reports"]),1)

    def test_stage437_replay_without_source_keeps_a0_reporting_opt_in(self):
        result=replay_private_gp0_clut_timeline(vram(),[E6,packet()],[BANK])
        self.assertEqual(result["a0_source_payload_reports"],[])
        self.assertFalse(result["decoded_stream_run_matching_enabled"])

    def test_private_main_entrypoint_with_mocked_original_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            before=root/"initial.u16le.bin";before.write_bytes(vram())
            trace=root/"gp0.jsonl";write_trace(trace,[E6,packet()])
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={
                           "map_index":2,"candidate_banks":[BANK],
                           "verified_streams":[stream()]}):
                result=audit_private_gp0_upload_timeline(root/"unused",before,trace)
            self.assertEqual(result["source_verified_lzss_stream_count"],1)
            self.assertEqual(result["counts"]["A0_SOURCE_BYTE_RUN_MATCHES"],1)

    def test_no_original_texture_or_packet_data_in_report(self):
        result=evaluate()
        report=json.dumps(result)
        for raw_field in ('"decoded_source_data"','"original_payload_words"',
                          '"game_palette_bytes"','"raw_a0_pixels"'):
            self.assertNotIn(raw_field,report)
        self.assertTrue(result["interpretation"][
            "all_metadata_and_sha256_fingerprints_owner_private"])


if __name__=="__main__":
    unittest.main()
