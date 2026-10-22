"""Stage443: synthetic-only A0-packet -> written VRAM words -> first-UV lineage."""
import json
from array import array
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_private_a0_draw_uv_lineage import PrivateA0DrawLineage
from audit_private_gp0_upload_timeline import (
    replay_private_gp0_clut_timeline, audit_private_gp0_upload_timeline)
from audit_private_gp0_a0_source_payload import match_a0_source_payload
from audit_private_surf_gp0_stream_uv_link import prepare_private_stream_index
from test_audit_private_gp0_upload_timeline import (
    BANK,E6,a0,vram,vram_copy,write_trace)
from test_audit_private_gp0_texture_first_uv import (
    E2_ZERO,E2_NONZERO,sample_polygon)
from test_audit_private_surf_gp0_stream_uv_link import SOURCE,stream,upload

def draw(u=80,page=0):
    return sample_polygon(u=u,page=page)

def play(packets,*,streams=None,max_evidence=20000):
    return replay_private_gp0_clut_timeline(
        vram(),packets,[BANK],
        source_streams=[stream()] if streams is None else streams,
        frame=443,max_evidence=max_evidence)

def event(report,position=0):
    return report["clut_draw_events"][position]["first_uv_direct_a0_lineage"]


class Stage443A0LineageTests(unittest.TestCase):
    def test_one_direct_a0_packet_covers_a_later_uv_draw(self):
        r=play([E2_ZERO,E6,upload(),draw()])
        item=event(r)
        self.assertEqual(item["status"],"CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV")
        self.assertEqual(item["last_direct_a0_writer_packet_index"],2)
        self.assertEqual(item["candidate_a0_matched_runs_covering_uv"],1)
        self.assertEqual(item["whole_run_refreshed_after_preceding_draw"],1)
        self.assertEqual(item["covering_runs"][0]["a0_packet_index"],2)
        self.assertEqual(item["covering_runs"][0]["source_offset_bytes"],0)
        self.assertTrue(item["interpretation"][
            "original_gpu_trace_origin_and_completeness_unverified"])

    def test_clut_or_visible_pixel_is_not_claimed_by_packet_link(self):
        r=play([E2_ZERO,E6,upload(),draw()])
        self.assertTrue(event(r)["interpretation"][
            "first_declared_uv_not_verified_visible_sample"])
        self.assertTrue(r["interpretation"][
            "matched_packet_to_uv_link_does_not_prove_real_gpu_execution"])

    def test_draw_without_source_a0_upload_reports_absence_of_direct_writer(self):
        r=play([E2_ZERO,draw()])
        self.assertEqual(event(r)["status"],
                         "NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")
        self.assertIsNone(event(r)["last_direct_a0_writer_packet_index"])

    def test_upload_to_unrelated_region_is_not_a_uv_packet_link(self):
        r=play([E2_ZERO,E6,upload(x=256),draw()])
        self.assertEqual(event(r)["status"],
                         "NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")

    def test_packet_with_nonmatching_source_bytes_can_write_uv_but_no_attribution(self):
        other=bytes((b^0xff) for b in SOURCE)
        r=play([E2_ZERO,E6,upload(raw=other),draw()])
        self.assertEqual(event(r)["status"],
                         "A0_WRITER_WITHOUT_MATCHED_SOURCE_RUN_AT_UV")
        self.assertEqual(event(r)["candidate_a0_matched_runs_covering_uv"],0)

    def test_later_single_word_a0_overwrites_first_uv_address(self):
        r=play([E2_ZERO,E6,upload(),a0(b"\x37\x12",x=20,y=0,width=1,height=1),draw()])
        self.assertEqual(event(r)["last_direct_a0_writer_packet_index"],3)
        self.assertEqual(event(r)["status"],
                         "A0_WRITER_WITHOUT_MATCHED_SOURCE_RUN_AT_UV")

    def test_later_single_word_overwrites_elsewhere_in_covering_run(self):
        r=play([E2_ZERO,E6,upload(),a0(b"\x37\x12",x=40,y=0,width=1,height=1),draw()])
        item=event(r)
        self.assertEqual(item["last_direct_a0_writer_packet_index"],2)
        self.assertEqual(item["candidate_a0_matched_runs_covering_uv"],1)
        self.assertEqual(item["whole_run_last_written_by_same_direct_a0_packet"],0)
        self.assertEqual(item["whole_run_refreshed_after_preceding_draw"],0)
        self.assertEqual(item["status"],"A0_SOURCE_RUN_COVERS_UV_BUT_FRESHNESS_UNVERIFIED")

    def test_two_draws_without_reupload_invalidate_freshness(self):
        r=play([E2_ZERO,E6,upload(),draw(),draw()])
        self.assertEqual(event(r,0)["status"],
                         "CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV")
        self.assertEqual(event(r,1)["status"],
                         "A0_SOURCE_RUN_COVERS_UV_BUT_FRESHNESS_UNVERIFIED")

    def test_reupload_after_draw_restores_fresh_a0_lineage(self):
        r=play([E2_ZERO,E6,upload(),draw(),upload(),draw()])
        self.assertEqual(event(r,0)["last_direct_a0_writer_packet_index"],2)
        self.assertEqual(event(r,1)["last_direct_a0_writer_packet_index"],4)
        self.assertTrue(all(event(r,k)["whole_run_refreshed_after_preceding_draw"]==1
                            for k in (0,1)))

    def test_vram_to_vram_copy_is_not_misclassified_as_direct_a0(self):
        r=play([E2_ZERO,E6,upload(x=256),
                vram_copy(sx=256,sy=19,dx=0,dy=19,width=16,height=1),
                vram_copy(sx=256,sy=19,dx=0,dy=0,width=16,height=1),
                draw(u=8)])
        item=event(r)
        self.assertEqual(item["status"],"NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")
        self.assertIsNone(item["last_direct_a0_writer_packet_index"])

    def test_copy_does_not_destroy_source_a0_writer(self):
        r=play([E2_ZERO,E6,upload(),
                vram_copy(sx=0,sy=0,dx=256,dy=0,width=16,height=1),
                draw()])
        self.assertEqual(event(r)["status"],
                         "CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV")

    def test_unknown_or_nonzero_e2_makes_packet_attribution_unavailable(self):
        for preamble in ([],[E2_NONZERO]):
            with self.subTest(preamble=preamble):
                r=play([*preamble,E6,upload(),draw()])
                self.assertEqual(event(r)["status"],
                    "FIRST_UV_NOT_AVAILABLE_FOR_A0_ATTRIBUTION")
                self.assertEqual(r["counts"]["A0_UV_LINEAGE_UNAVAILABLE"],1)

    def test_non_four_bit_depth_has_no_false_first_uv_linkage(self):
        r=play([E2_ZERO,E6,upload(),draw(page=0x80)])
        self.assertEqual(r["clut_draw_events"],[])
        self.assertEqual(r["counts"]["TEXTURED_NOT_4BPP"],1)

    def test_source_streams_not_given_preserves_old_opt_in_behavior(self):
        r=replay_private_gp0_clut_timeline(
            vram(),[E2_ZERO,E6,upload(),draw()],[BANK])
        self.assertIsNone(
            r["clut_draw_events"][0]["first_uv_direct_a0_lineage"])

    def test_multiple_identical_streams_remain_explicitly_ambiguous(self):
        r=play([E2_ZERO,E6,upload(),draw()],
               streams=[stream(),stream(region=8)])
        item=event(r)
        self.assertEqual(item["candidate_a0_matched_runs_covering_uv"],2)
        self.assertEqual(item["whole_run_refreshed_after_preceding_draw"],2)
        self.assertEqual(
            {x["graphics_region_index"] for x in item["covering_runs"]},{6,8})

    def test_uncertainty_if_matching_packet_samples_are_truncated(self):
        evidence=PrivateA0DrawLineage()
        # A0 writes the word, but no complete source-run samples were saved.
        evidence.record_a0(7,0,0,96,1,{"run_samples":[],
                                         "sample_truncated":True})
        info=evidence.inspect(20,0,0,array("i",[0])*524288)
        self.assertEqual(info["status"],
            "A0_SOURCE_MATCH_SAMPLES_TRUNCATED_CANNOT_EXCLUDE_LINK")
        self.assertTrue(info["sample_truncated"])

    def test_packet_samples_capped_but_lineage_counters_remain_complete(self):
        r=play([E2_ZERO,E6,upload(),draw(),upload(),draw()],
               max_evidence=1)
        self.assertEqual(len(r["clut_draw_events"]),1)
        self.assertEqual(r["counts"][
            "A0_UV_LINEAGE_CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV"],2)

    def test_direct_a0_packet_sample_bounds_are_checked(self):
        evidence=PrivateA0DrawLineage()
        invalid={"run_samples":[{
            "a0_destination_x_words":100,
            "a0_destination_y":0,
            "matched_byte_span":192,
            "graphics_region_index":6,
            "source_offset_bytes":0,
            "candidate_stream_ordinal":0}], "sample_truncated":False}
        with self.assertRaisesRegex(ValueError,"outside"):
            evidence.record_a0(1,0,0,96,1,invalid)

    def test_copy_destination_marked_unknown_after_valid_lineage(self):
        tracker=PrivateA0DrawLineage()
        sample={"run_samples":[{
            "a0_destination_x_words":0,"a0_destination_y":0,
            "matched_byte_span":192,"graphics_region_index":6,
            "source_offset_bytes":0,"candidate_stream_ordinal":0}],
            "sample_truncated":False}
        tracker.record_a0(1,0,0,96,1,sample)
        tracker.invalidate_vram_copy_destination(0,0,96,1)
        item=tracker.inspect(20,0,0,array("i",[0])*524288)
        self.assertEqual(item["status"],"NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")

    def test_private_entrypoint_includes_direct_packet_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            initial=root/"initial.bin";initial.write_bytes(vram())
            trace=root/"trace.jsonl";write_trace(
                trace,[E2_ZERO,E6,upload(),draw()],frame=12)
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[stream()]}):
                r=audit_private_gp0_upload_timeline(
                    root/"not_a_real_cdstg",initial,trace)
            self.assertEqual(event(r)["status"],
                         "CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV")

    def test_metadata_contains_no_original_packet_or_palette_bytes(self):
        r=play([E2_ZERO,E6,upload(),draw()])
        raw=json.dumps(r)
        for field in ('"raw_gp0_packet_words"','"source_decoded_bytes"',
                      '"original_clut_u16"','"source_pixel_indices"'):
            self.assertNotIn(field,raw)
        self.assertTrue(event(r)["interpretation"][
            "no_original_texture_bytes_or_palette_words_exported"])

    def test_direct_lineage_mismatch_with_genuine_capture_is_still_unverified(self):
        r=play([E2_ZERO,E6,upload(),draw()])
        self.assertTrue(event(r)["interpretation"][
            "original_gpu_trace_origin_and_completeness_unverified"])
        self.assertTrue(r["interpretation"][
            "matched_packet_to_uv_link_does_not_prove_real_gpu_execution"])


if __name__=="__main__":
    unittest.main()
