"""Stage444 ROM-free direct-vs-transitive GP0(80) A0 source-run lineage."""
from array import array
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_private_a0_transitive_copy_lineage import PrivateA0CopyLineage
from audit_private_gp0_upload_timeline import (
    replay_private_gp0_clut_timeline, audit_private_gp0_upload_timeline,
)
from test_audit_private_gp0_upload_timeline import (
    BANK, E6, a0, vram, vram_copy, write_trace,
)
from test_audit_private_gp0_texture_first_uv import (
    E2_ZERO, E2_NONZERO, sample_polygon,
)
from test_audit_private_surf_gp0_stream_uv_link import SOURCE, stream, upload

COUNT=1024*512


def draw(*, u=80, v=0, page=4):
    return sample_polygon(u=u,v=v,page=page)


def copy(*, sx=0, sy=0, dx=256, dy=0, width=96, height=1):
    return vram_copy(sx=sx,sy=sy,dx=dx,dy=dy,width=width,height=height)


def play(packets, *, sources=None, cap=20000):
    return replay_private_gp0_clut_timeline(
        vram(), packets, [BANK],
        source_streams=[stream()] if sources is None else sources,
        frame=444, max_evidence=cap)


def transitive(result, event_index=0):
    return result["clut_draw_events"][event_index][
        "first_uv_transitive_a0_copy_lineage"]


def direct(result, event_index=0):
    return result["clut_draw_events"][event_index][
        "first_uv_direct_a0_lineage"]


class Stage444CopyChainTests(unittest.TestCase):
    def test_without_copy_keeps_direct_origin_and_zero_hops(self):
        out=play([E2_ZERO,E6,upload(),draw(page=0)])
        a=transitive(out)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")
        self.assertEqual(a["first_uv_copy_hops"],0)
        self.assertEqual(a["whole_run_fresh_since_previous_draw"],1)
        self.assertEqual(direct(out)["status"],
                         "CONDITIONAL_FRESH_A0_SOURCE_RUN_COVERS_FIRST_UV")

    def test_one_full_copy_preserves_original_packet_but_not_direct_writer(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw()])
        a=transitive(out)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")
        self.assertEqual(a["source_a0_packet_index"],2)
        self.assertEqual(a["first_uv_copy_hops"],1)
        self.assertEqual(a["candidate_original_a0_runs_covering_uv"],1)
        self.assertEqual(a["whole_run_remains_contiguous_from_same_a0"],1)
        self.assertEqual(a["run_samples"][0]["minimum_copy_hops"],1)
        self.assertEqual(a["run_samples"][0]["maximum_copy_hops"],1)
        self.assertEqual(a["run_samples"][0]["current_run_start_x_words"],256)
        self.assertEqual(direct(out)["status"],
                         "NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")

    def test_two_consecutive_full_copies_keep_original_a0_origin(self):
        out=play([E2_ZERO,E6,upload(),copy(),copy(sx=256,dx=512),
                  draw(page=8)])
        a=transitive(out)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")
        self.assertEqual(a["source_a0_packet_index"],2)
        self.assertEqual(a["first_uv_copy_hops"],2)
        self.assertEqual(a["run_samples"][0]["maximum_copy_hops"],2)
        self.assertEqual(a["run_samples"][0]["current_run_start_x_words"],512)

    def test_unknown_pretrace_vram_cannot_establish_origin_after_copy(self):
        out=play([E2_ZERO,E6,copy(),draw()])
        self.assertEqual(transitive(out)["status"],
                         "NO_KNOWN_A0_ORIGIN_FOR_FIRST_UV")
        self.assertIsNone(transitive(out)["source_a0_packet_index"])

    def test_partial_copy_does_not_promote_one_word_into_full_source_run(self):
        out=play([E2_ZERO,E6,upload(),copy(width=48),draw()])
        a=transitive(out)
        self.assertEqual(a["status"],
                         "PARTIAL_OR_REORDERED_SOURCE_RUN_NOT_PROVEN")
        self.assertEqual(a["whole_run_remains_contiguous_from_same_a0"],0)
        self.assertEqual(a["candidate_original_a0_runs_covering_uv"],1)

    def test_overwrite_one_other_word_in_copied_run_fails_full_span(self):
        out=play([E2_ZERO,E6,upload(),copy(),
                  a0(b"\x37\x12",x=300,y=0,width=1,height=1),draw()])
        a=transitive(out)
        self.assertEqual(a["source_a0_packet_index"],2)
        self.assertEqual(a["status"],
                         "PARTIAL_OR_REORDERED_SOURCE_RUN_NOT_PROVEN")
        self.assertEqual(a["whole_run_fresh_since_previous_draw"],0)

    def test_overwrite_selected_word_replaces_original_packet(self):
        out=play([E2_ZERO,E6,upload(),copy(),
                  a0(b"\x37\x12",x=276,y=0,width=1,height=1),draw()])
        a=transitive(out)
        self.assertEqual(a["source_a0_packet_index"],4)
        self.assertEqual(a["status"],
                         "A0_ORIGIN_WITH_NO_MATCHED_SOURCE_RUN_AT_UV")

    def test_two_correct_half_copies_can_reconstitute_entire_original_run(self):
        out=play([E2_ZERO,E6,upload(),
                  copy(width=48),copy(sx=48,dx=304,width=48),draw()])
        a=transitive(out)
        self.assertEqual(a["whole_run_remains_contiguous_from_same_a0"],1)
        self.assertEqual(a["whole_run_fresh_since_previous_draw"],1)

    def test_swapped_halves_do_not_qualify_as_contiguous_original_run(self):
        out=play([E2_ZERO,E6,upload(),
                  copy(sx=48,dx=256,width=48),
                  copy(sx=0,dx=304,width=48),draw()])
        self.assertEqual(transitive(out)["status"],
                         "PARTIAL_OR_REORDERED_SOURCE_RUN_NOT_PROVEN")

    def test_preceding_draw_invalidates_freshness_of_later_copy(self):
        out=play([E2_ZERO,E6,upload(),draw(page=0),
                  copy(),draw()])
        a=transitive(out,1)
        self.assertEqual(a["whole_run_remains_contiguous_from_same_a0"],1)
        self.assertEqual(a["whole_run_fresh_since_previous_draw"],0)
        self.assertEqual(a["status"],
                         "TRANSITIVE_SOURCE_RUN_WITH_UNVERIFIED_FRESHNESS")

    def test_upload_then_copy_after_draw_restores_freshness(self):
        out=play([E2_ZERO,E6,upload(),draw(page=0),
                  upload(),copy(),draw()])
        a=transitive(out,1)
        self.assertEqual(a["source_a0_packet_index"],4)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")

    def test_copy_to_another_row_links_first_uv_with_v_coordinate(self):
        out=play([E2_ZERO,E6,upload(),copy(dy=20),
                  draw(page=4,v=20)])
        a=transitive(out)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")
        self.assertEqual(a["source_a0_word_y"],0)
        self.assertEqual(a["first_uv_y"],20)
        self.assertEqual(a["run_samples"][0]["current_run_y"],20)

    def test_copy_to_last_valid_vram_row_is_bounded(self):
        out=play([E2_ZERO,E6,upload(),
                  copy(dx=928,dy=511),
                  draw(page=14,u=208,v=255)])
        # page=14 sets y=0, so v=255 cannot select VRAM row 511.
        # No false lineage should appear at a different row.
        self.assertEqual(transitive(out)["status"],
                         "NO_KNOWN_A0_ORIGIN_FOR_FIRST_UV")

    def test_mixed_hop_counts_still_validate_consecutive_origin_words(self):
        out=play([E2_ZERO,E6,upload(),copy(),
                  copy(sx=256,dx=512,width=48),
                  copy(sx=48,dx=560,width=48),
                  draw(page=8)])
        a=transitive(out)
        self.assertEqual(a["status"],"CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN")
        run=a["run_samples"][0]
        self.assertEqual(run["minimum_copy_hops"],1)
        self.assertEqual(run["maximum_copy_hops"],2)

    def test_two_identical_candidate_streams_are_not_declared_unique(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw()],
                 sources=[stream(),stream(region=8)])
        a=transitive(out)
        self.assertEqual(a["candidate_original_a0_runs_covering_uv"],2)
        self.assertEqual(a["whole_run_fresh_since_previous_draw"],2)
        self.assertEqual({s["graphics_region_index"] for s in a["run_samples"]},
                         {6,8})

    def test_unknown_gp0_e2_window_suppresses_attribution(self):
        for prefix in ([],[E2_NONZERO]):
            with self.subTest(prefix=prefix):
                out=play([*prefix,E6,upload(),copy(),draw()])
                self.assertEqual(transitive(out)["status"],
                    "FIRST_UV_UNAVAILABLE_FOR_COPY_LINEAGE")
                self.assertEqual(out["counts"]["A0_COPY_LINEAGE_UNAVAILABLE"],1)

    def test_copy_chain_counter_not_limited_by_event_sample_cap(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw(),draw(),draw()],cap=1)
        self.assertEqual(len(out["clut_draw_events"]),1)
        self.assertEqual(out["counts"][
            "A0_COPY_LINEAGE_TRANSITIVE_SOURCE_RUN_WITH_UNVERIFIED_FRESHNESS"],2)
        self.assertEqual(out["counts"][
            "A0_COPY_LINEAGE_CONDITIONAL_FRESH_TRANSITIVE_SOURCE_RUN"],1)

    def test_unproven_original_a0_samples_remain_inconclusive(self):
        lineage=PrivateA0CopyLineage()
        lineage.record_a0(5,0,0,96,1,
                          {"run_samples":[],"sample_truncated":True})
        lineage.copy_vram(0,0,256,0,96,1)
        a=lineage.inspect_copy_lineage(276,0,0,array("i",[0])*COUNT)
        self.assertEqual(a["status"],"SOURCE_MATCH_SAMPLES_TRUNCATED")
        self.assertTrue(a["sample_truncated_or_unknown"])

    def test_overlapping_copy_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"overlapping"):
            PrivateA0CopyLineage().copy_vram(0,0,32,0,96,1)

    def test_invalid_copy_geometry_fails_closed(self):
        l=PrivateA0CopyLineage()
        for vals in ((-1,0,256,0,96,1),(0,0,1000,0,96,1),
                     (0,0,256,511,96,2),(0,0,256,0,True,1)):
            with self.subTest(values=vals),self.assertRaises(ValueError):
                l.copy_vram(*vals)

    def test_empty_source_streams_preserve_opt_in_behavior(self):
        out=replay_private_gp0_clut_timeline(
            vram(),[E2_ZERO,E6,upload(),copy(),draw()],[BANK])
        self.assertIsNone(out["clut_draw_events"][0][
            "first_uv_transitive_a0_copy_lineage"])

    def test_direct_stage443_semantics_preserved_after_copy(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw()])
        self.assertIsNone(direct(out)["last_direct_a0_writer_packet_index"])
        self.assertEqual(transitive(out)["source_a0_packet_index"],2)
        self.assertTrue(out["interpretation"][
            "copy_origin_is_not_a_direct_a0_writer_at_destination"])

    def test_full_owner_private_entrypoint_with_synthetic_trace(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            initial=root/"initial.bin"; initial.write_bytes(vram())
            trace=root/"trace.jsonl"
            write_trace(trace,[E2_ZERO,E6,upload(),copy(),draw()],frame=12)
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[stream()]}):
                out=audit_private_gp0_upload_timeline(root/"no-real-data",initial,trace)
            self.assertEqual(out["source_map_index"],2)
            self.assertEqual(transitive(out)["first_uv_copy_hops"],1)

    def test_metadata_does_not_export_source_bytes_or_gp0_words(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw()])
        raw=json.dumps(out)
        for field in ('"raw_gp0_packet"','"source_decoded_bytes"',
                      '"original_texture_word"','"palette_color_u16"'):
            self.assertNotIn(field,raw)
        self.assertTrue(transitive(out)["interpretation"][
            "no_raw_texture_color_vram_or_gp0_data_exported"])

    def test_no_matching_run_does_not_claim_origin_proof(self):
        out=play([E2_ZERO,E6,upload(),copy(),draw()],
                 sources=[stream(bytes(192))])
        self.assertEqual(transitive(out)["status"],
                         "A0_ORIGIN_WITH_NO_MATCHED_SOURCE_RUN_AT_UV")


if __name__=="__main__":
    unittest.main()
