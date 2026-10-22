"""Stage441: ROM-free source run that covers the *modeled pre-draw* first UV."""
from array import array
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_private_surf_gp0_stream_uv_link import (  # noqa: E402
    match_first_uv_to_private_streams,prepare_private_stream_index)
from audit_private_gp0_upload_timeline import (  # noqa: E402
    VRAM_BYTES,replay_private_gp0_clut_timeline,
    audit_private_gp0_upload_timeline)
from test_audit_private_gp0_upload_timeline import (  # noqa: E402
    BANK,E6,a0,vram,write_trace)
from test_audit_private_gp0_texture_first_uv import (  # noqa: E402
    E2_ZERO,E2_NONZERO,sample_polygon)

SOURCE=bytes((i*19 + i//64*29 + 5)%256 for i in range(192))
REGION=6
WORDS=524288


def stream(raw=SOURCE,region=REGION):
    return {"graphics_region_index":region,"decoded":raw}


def model(packets,*,streams=None,max_evidence=20000,initial=None):
    return replay_private_gp0_clut_timeline(
        vram() if initial is None else initial,packets,[BANK],
        source_streams=streams,max_evidence=max_evidence,frame=441)


def upload(raw=SOURCE,*,x=0,y=0):
    return a0(raw,x=x,y=y,width=len(raw)//2,height=1)


def sample(*,u=80,v=0,page=0):
    return sample_polygon(u=u,v=v,page=page)


def memory_at(raw=SOURCE,*,x_words=0,y=0):
    original=bytearray(VRAM_BYTES)
    at=y*2048 + x_words*2
    original[at:at+len(raw)]=raw
    return bytes(original)


def match(memory,*,x=20,y=0,streams=None,epoch=None,draw=0,**kwargs):
    candidates=[stream()] if streams is None else streams
    index=prepare_private_stream_index(candidates)
    states=(array("i",[-1])*WORDS if epoch is None else epoch)
    return match_first_uv_to_private_streams(
        index,memory,x,y,states,draw,**kwargs)


class Stage441SourceUVTests(unittest.TestCase):
    def test_direct_source_run_covers_first_uv_word(self):
        report=match(memory_at())
        self.assertEqual(report["covering_byte_identical_run_count"],1)
        item=report["covering_runs"][0]
        self.assertEqual(item["graphics_region_index"],REGION)
        self.assertEqual(item["source_offset_bytes"],0)
        self.assertEqual(item["modeled_vram_run_start_x_words"],0)
        self.assertEqual(item["matched_contiguous_64byte_blocks"],3)
        self.assertEqual(item["first_uv_offset_within_run_bytes"],40)
        self.assertEqual(item["run_sha256"],hashlib.sha256(SOURCE).hexdigest())
        self.assertFalse(item["all_run_halfwords_explicitly_written_since_last_draw"])

    def test_integrated_gpu_upload_then_uv_draw_has_conditional_link(self):
        report=model([E2_ZERO,E6,upload(),sample()],streams=[stream()])
        event=report["clut_draw_events"][0]
        bridge=event["first_uv_source_run_linkage"]
        self.assertEqual(bridge["status"],"FIRST_UV_SOURCE_RUN_COVERAGE_SCANNED")
        self.assertEqual(bridge["covering_byte_identical_run_count"],1)
        self.assertEqual(bridge["covering_runs_fully_refreshed_since_last_draw"],1)
        self.assertTrue(bridge["covering_runs"][0][
            "all_run_halfwords_explicitly_written_since_last_draw"])
        self.assertTrue(report["decoded_stream_run_matching_enabled"])
        self.assertEqual(report["indexed_candidate_decoded_stream_count"],1)
        self.assertEqual(report["counts"]["UV_SOURCE_LINKAGE_DRAWS_WITH_RUN"],1)

    def test_baseline_byte_match_is_not_asserted_as_draw_time_transfer(self):
        report=model([E2_ZERO,sample()],
                     streams=[stream()],initial=memory_at())
        item=report["clut_draw_events"][0]["first_uv_source_run_linkage"]
        self.assertEqual(item["covering_byte_identical_run_count"],1)
        self.assertEqual(item["covering_runs_fully_refreshed_since_last_draw"],0)
        self.assertTrue(item["source_to_texture_page_mapping_not_authenticated"])

    def test_changed_middle_block_breaks_run(self):
        altered=bytearray(SOURCE)
        altered[75] ^= 1
        report=match(memory_at(bytes(altered)))
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_short_128_byte_match_does_not_qualify(self):
        report=match(memory_at(SOURCE[:128]))
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_first_uv_outside_matching_run_is_not_linked(self):
        report=match(memory_at(),x=100)
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_first_uv_at_final_halfword_of_run_is_included(self):
        report=match(memory_at(),x=95)
        self.assertEqual(report["covering_byte_identical_run_count"],1)
        self.assertEqual(report["covering_runs"][0]["first_uv_offset_within_run_bytes"],190)

    def test_unaligned_source_to_vram_copy_ignored(self):
        report=match(memory_at(x_words=1),x=20)
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_run_may_not_cross_vram_scanline(self):
        report=match(memory_at(x_words=960,y=10),x=990,y=10)
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_low_information_source_blocks_are_filtered(self):
        report=match(memory_at(bytes(192)),
                     streams=[stream(bytes(192))],x=20)
        self.assertEqual(report["covering_byte_identical_run_count"],0)

    def test_too_frequent_anchor_is_not_used_as_proof(self):
        blob=SOURCE[:64]*17
        index=prepare_private_stream_index([stream(blob)])
        self.assertEqual(index["eligible_distinct_anchor_count"],0)
        result=match_first_uv_to_private_streams(
            index,memory_at(blob),20,0,array("i",[-1])*WORDS,0)
        self.assertEqual(result["covering_byte_identical_run_count"],0)

    def test_duplicate_source_streams_remain_ambiguous(self):
        report=match(memory_at(),streams=[stream(),stream(region=7)])
        self.assertEqual(report["covering_byte_identical_run_count"],2)
        self.assertEqual({r["graphics_region_index"] for r in report["covering_runs"]},
                         {6,7})

    def test_max_evidence_samples_does_not_truncate_full_counts(self):
        report=match(memory_at(),streams=[stream(),stream(region=7)],
                     max_match_samples=1)
        self.assertEqual(report["covering_byte_identical_run_count"],2)
        self.assertEqual(report["reported_covering_run_count"],1)
        self.assertTrue(report["covering_run_samples_truncated"])

    def test_uncertain_window_refuses_to_make_stream_link(self):
        for seq in ([E6,upload(),sample()],
                    [E2_NONZERO,E6,upload(),sample()]):
            with self.subTest(seq=seq):
                report=model(seq,streams=[stream()])
                item=report["clut_draw_events"][0]["first_uv_source_run_linkage"]
                self.assertEqual(item["status"],"FIRST_UV_TEXTURE_ADDRESS_UNAVAILABLE")
                self.assertTrue(item["no_source_run_match_attempted"])
                self.assertEqual(report["counts"]["UV_SOURCE_LINKAGE_UNAVAILABLE"],1)

    def test_no_source_data_mode_still_supports_old_stage439(self):
        report=model([E2_ZERO,E6,upload(),sample()])
        self.assertIsNone(report["clut_draw_events"][0]["first_uv_source_run_linkage"])
        self.assertFalse(report["decoded_stream_run_matching_enabled"])

    def test_old_stage438_postframe_reconciliation_still_works(self):
        output=memory_at()
        report=replay_private_gp0_clut_timeline(
            vram(),[E2_ZERO,E6,upload()],[BANK],
            source_streams=[stream()],observed_post_vram=output,
            require_post_match=True)
        self.assertTrue(report["postframe_reconciliation"]["all_comparable_words_match"])

    def test_qualified_run_not_fresh_when_upload_precedes_other_draw(self):
        report=model([E2_ZERO,E6,upload(),sample(),sample()],
                     streams=[stream()])
        first,second=(r["first_uv_source_run_linkage"]
                      for r in report["clut_draw_events"])
        self.assertEqual(first["covering_runs_fully_refreshed_since_last_draw"],1)
        self.assertEqual(second["covering_runs_fully_refreshed_since_last_draw"],0)

    def test_source_run_after_draw_reupload_refreshes_known_words(self):
        report=model([E2_ZERO,E6,upload(),sample(),upload(),sample()],
                     streams=[stream()])
        self.assertTrue(all(event["first_uv_source_run_linkage"][
            "covering_runs_fully_refreshed_since_last_draw"]==1
            for event in report["clut_draw_events"]))

    def test_capped_gpu_event_samples_still_count_all_matching_draws(self):
        report=model([E2_ZERO,E6,upload(),sample(),sample(),sample()],
                     streams=[stream()],max_evidence=1)
        self.assertEqual(len(report["clut_draw_events"]),1)
        self.assertEqual(report["counts"]["UV_SOURCE_LINKAGE_DRAWS_WITH_RUN"],3)
        self.assertEqual(report["counts"]["UV_SOURCE_LINKAGE_COVERING_RUNS"],3)

    def test_run_ends_at_vram_row_boundary_without_crossing(self):
        report=match(memory_at(x_words=928,y=511),x=1023,y=511)
        self.assertEqual(report["covering_byte_identical_run_count"],1)
        self.assertEqual(report["covering_runs"][0]["modeled_vram_run_y"],511)

    def test_validation_rejects_wrong_source_geometry_and_bad_arguments(self):
        for record in (
            {"decoded":b"short","graphics_region_index":6},
            {"decoded":SOURCE[:-1],"graphics_region_index":6},
            {"decoded":SOURCE,"graphics_region_index":True},
        ):
            with self.subTest(record=record),self.assertRaises(ValueError):
                prepare_private_stream_index([record])
        with self.assertRaises(ValueError):
            prepare_private_stream_index([stream()],minimum_distinct_bytes=True)
        with self.assertRaises(ValueError):
            match(memory_at(),x=True)
        with self.assertRaises(ValueError):
            match(memory_at(),x=1024)
        with self.assertRaises(ValueError):
            match(memory_at(),max_match_samples=0)

    def test_end_to_end_private_entrypoint_uses_verified_decoded_streams(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            first=root/"pre.u16le.bin"
            first.write_bytes(vram())
            packets=root/"packets.jsonl"
            write_trace(packets,[E2_ZERO,E6,upload(),sample()],frame=12)
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={
                           "map_index":2,"candidate_banks":[BANK],
                           "verified_streams":[stream()] }):
                report=audit_private_gp0_upload_timeline(
                    root/"synthetic-disc-not-required",first,packets)
            linkage=report["clut_draw_events"][0]["first_uv_source_run_linkage"]
            self.assertEqual(linkage["covering_byte_identical_run_count"],1)
            self.assertEqual(report["source_verified_lzss_stream_count"],1)

    def test_privacy_no_decoded_source_payload_in_json(self):
        report=model([E2_ZERO,E6,upload(),sample()],streams=[stream()])
        encoded=json.dumps(report)
        for field in ('"decoded"','"raw_source_bytes"','"texture_index_u4"',
                      '"original_color_u16"','"gp0_words"'):
            self.assertNotIn(field,encoded)
        item=report["clut_draw_events"][0]["first_uv_source_run_linkage"]
        self.assertTrue(item["no_source_pixel_words_or_decoded_stream_bytes_exported"])
        self.assertTrue(item["matching_bytes_not_proof_of_gpu_upload_or_visible_texture"])


if __name__=="__main__":
    unittest.main()
