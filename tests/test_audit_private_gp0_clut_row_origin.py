"""Stage445 synthetic-only candidate palette-row origin and first-UV CLUT checks."""
from pathlib import Path
import sys
import json
import hashlib
import tempfile
import unittest
from array import array
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from audit_private_gp0_clut_row_origin import inspect_private_clut_row_lineage
from audit_private_a0_transitive_copy_lineage import PrivateA0CopyLineage
from audit_private_gp0_upload_timeline import (
    replay_private_gp0_clut_timeline, audit_private_gp0_upload_timeline)
from test_audit_private_gp0_upload_timeline import (
    BANK,COLORS,E6,a0,vram,vram_copy,polygon,write_trace)
from test_audit_private_gp0_texture_first_uv import (
    E2_ZERO,E2_NONZERO,texture_packet)
from test_audit_private_surf_gp0_stream_uv_link import SOURCE,stream,upload

def draw(*,palette_x=32,palette_y=19,u=3):
    command=polygon(x=palette_x,y=palette_y,page=0)
    command[2]=(command[2]&0xffff0000)|u
    return command

def play(packets,*,bank=None,banks=None,max_evidence=20000):
    return replay_private_gp0_clut_timeline(
        vram(),packets,
        [BANK] if bank is None and banks is None else (
            banks if banks is not None else [bank]),
        source_streams=[stream()],frame=445,max_evidence=max_evidence)

def palette(result,which=0):
    return result["clut_draw_events"][which]["first_uv_clut_row_origin"]

def setup_packets():
    return [E2_ZERO,E6,a0(COLORS),texture_packet(),draw()]

class Stage445CLUTRowTests(unittest.TestCase):
    def test_independent_texture_and_palette_a0_sources_are_visible(self):
        report=play(setup_packets())
        p=palette(report)
        self.assertEqual(p["status"],"CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")
        self.assertEqual(p["selected_clut_origin_a0_packet_index"],2)
        self.assertEqual(p["texture_halfword_origin_a0_packet_index"],3)
        self.assertFalse(p["texture_and_clut_selected_halfwords_share_original_a0_packet"])
        self.assertEqual((p["clut_x_words"],p["clut_y"]),(32,19))
        self.assertEqual(p["matching_source_palette_row_count"],1)
        self.assertEqual(p["matching_source_palette_rows"],
                         [{"candidate_bank_index":0,"candidate_row_index":0}])
        self.assertTrue(p["entire_clut_row_has_contiguous_same_a0_origin"])
        self.assertTrue(p["entire_clut_row_fresh_since_last_draw"])
        self.assertTrue(p["both_selected_palette_and_texture_fresh_since_last_draw"])
        self.assertEqual(p["all_clut_row_copy_hops_min"],0)
        self.assertEqual(p["all_clut_row_copy_hops_max"],0)

    def test_first_uv_nibble_is_recorded_as_position_not_color_index(self):
        report=play(setup_packets())
        probe=report["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertEqual(probe["first_uv_nibble_within_u16"],3)
        self.assertEqual(palette(report)["selected_clut_word_x_words"],35)
        self.assertEqual(palette(report)["selected_clut_word_y"],19)

    def test_full_clut_row_copy_has_transitive_a0_origin(self):
        report=play([E2_ZERO,E6,a0(COLORS),
                     vram_copy(sx=32,sy=19,dx=64,dy=19,width=16,height=1),
                     texture_packet(),draw(palette_x=64)])
        p=palette(report)
        self.assertEqual(p["status"],"CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")
        self.assertEqual(p["selected_clut_origin_a0_packet_index"],2)
        self.assertEqual(p["all_clut_row_copy_hops_min"],1)
        self.assertEqual(p["all_clut_row_copy_hops_max"],1)
        self.assertEqual(p["matching_source_palette_row_count"],1)

    def test_duplicate_clut_bank_rows_do_not_become_unique(self):
        report=play(setup_packets(),banks=[BANK,BANK])
        p=palette(report)
        self.assertEqual(p["matching_source_palette_row_count"],2)
        self.assertEqual({x["candidate_bank_index"]
                          for x in p["matching_source_palette_rows"]},{0,1})

    def test_second_draw_without_reupload_has_stale_candidate_row(self):
        report=play(setup_packets()+[draw()])
        first,second=palette(report,0),palette(report,1)
        self.assertEqual(first["status"],
                         "CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")
        self.assertEqual(second["status"],
                         "CANDIDATE_CLUT_ROW_ORIGIN_WITH_UNVERIFIED_FRESHNESS")
        self.assertFalse(second["entire_clut_row_fresh_since_last_draw"])

    def test_reupload_restores_freshness_after_intervening_draw(self):
        report=play(setup_packets()+[a0(COLORS),texture_packet(),draw()])
        self.assertEqual(palette(report,1)["status"],
                         "CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")
        self.assertTrue(palette(report,1)["both_selected_palette_and_texture_fresh_since_last_draw"])

    def test_partial_row_copy_fails_to_prove_complete_palette_origin(self):
        report=play([E2_ZERO,E6,a0(COLORS),
                     vram_copy(sx=32,sy=19,dx=64,dy=19,width=8,height=1),
                     texture_packet(),draw(palette_x=64)])
        self.assertEqual(palette(report)["status"],
                         "NO_DECODED_SOURCE_PALETTE_ROW_MATCH")
        self.assertFalse(palette(report)["entire_clut_row_has_contiguous_same_a0_origin"])

    def test_mixed_a0_row_can_still_equal_palette_bytes_without_uniform_origin(self):
        report=play([E2_ZERO,E6,a0(COLORS),
                     a0(COLORS[2:4],x=33,y=19,width=1,height=1),
                     texture_packet(),draw()])
        p=palette(report)
        self.assertEqual(p["status"],"CANDIDATE_ROW_WITH_PARTIAL_OR_MIXED_A0_ORIGINS")
        self.assertFalse(p["entire_clut_row_has_contiguous_same_a0_origin"])
        self.assertTrue(p["entire_clut_row_fresh_since_last_draw"])

    def test_selected_clut_halfword_overwrite_updates_its_packet_index(self):
        report=play([E2_ZERO,E6,a0(COLORS),
                     a0(COLORS[6:8],x=35,y=19,width=1,height=1),
                     texture_packet(),draw()])
        p=palette(report)
        self.assertEqual(p["selected_clut_origin_a0_packet_index"],3)
        self.assertFalse(p["entire_clut_row_has_contiguous_same_a0_origin"])

    def test_original_baseline_palette_match_cannot_assert_a0_origin(self):
        initial=vram(x=32,y=19)
        report=replay_private_gp0_clut_timeline(
            initial,[E2_ZERO,E6,texture_packet(),draw()],[BANK],
            source_streams=[stream()])
        p=palette(report)
        self.assertEqual(p["status"],"CANDIDATE_ROW_WITHOUT_KNOWN_A0_ORIGIN")
        self.assertIsNone(p["selected_clut_origin_a0_packet_index"])

    def test_palette_row_not_in_source_banks_is_not_candidate(self):
        report=play(setup_packets(),bank=bytes(512))
        self.assertEqual(palette(report)["status"],
                         "NO_DECODED_SOURCE_PALETTE_ROW_MATCH")
        self.assertEqual(palette(report)["matching_source_palette_row_count"],0)

    def test_texture_window_unknown_refuses_to_guess_selected_entry(self):
        report=play([E6,a0(COLORS),texture_packet(),draw()])
        p=palette(report)
        self.assertEqual(p["status"],"FIRST_UV_UNAVAILABLE_CLUT_ENTRY_NOT_EVALUATED")
        self.assertNotIn("selected_clut_origin_a0_packet_index",p)

    def test_nonzero_texture_window_refuses_to_guess_selected_entry(self):
        report=play([E2_NONZERO,E6,a0(COLORS),texture_packet(),draw()])
        self.assertEqual(palette(report)["status"],
                         "FIRST_UV_UNAVAILABLE_CLUT_ENTRY_NOT_EVALUATED")

    def test_explicit_zero_e2_reestablishes_palette_probe(self):
        report=play([E2_NONZERO,E2_ZERO,E6,a0(COLORS),
                     texture_packet(),draw()])
        self.assertEqual(palette(report)["status"],
                         "CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")

    def test_copy_after_draw_does_not_reestablish_source_color_freshness(self):
        report=play([E2_ZERO,E6,a0(COLORS),texture_packet(),draw(),
                     vram_copy(sx=32,sy=19,dx=64,dy=19,width=16,height=1),
                     draw(palette_x=64)])
        p=palette(report,1)
        self.assertEqual(p["status"],
                         "CANDIDATE_CLUT_ROW_ORIGIN_WITH_UNVERIFIED_FRESHNESS")
        self.assertFalse(p["entire_clut_row_fresh_since_last_draw"])

    def test_full_palette_and_tex_upload_after_draw_refresh_both(self):
        report=play(setup_packets()+[a0(COLORS),texture_packet(),draw()])
        self.assertTrue(palette(report,1)[
            "both_selected_palette_and_texture_fresh_since_last_draw"])

    def test_sample_cap_does_not_hide_clut_origin_counters(self):
        report=play(setup_packets()+[draw(),draw()],max_evidence=1)
        self.assertEqual(len(report["clut_draw_events"]),1)
        self.assertEqual(report["counts"]["CLUT_ROW_ORIGIN_CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN"],1)
        self.assertEqual(report["counts"]["CLUT_ROW_ORIGIN_CANDIDATE_CLUT_ROW_ORIGIN_WITH_UNVERIFIED_FRESHNESS"],2)

    def test_first_uv_and_clut_reports_stay_distinct(self):
        r=play(setup_packets())
        e=r["clut_draw_events"][0]
        self.assertIn("first_uv_direct_a0_lineage",e)
        self.assertIn("first_uv_transitive_a0_copy_lineage",e)
        self.assertIn("first_uv_clut_row_origin",e)
        self.assertTrue(r["interpretation"][
            "palette_origin_equality_does_not_authenticate_gpu_clut_sampling"])

    def test_reject_inconsistent_hash_probe(self):
        tracker=PrivateA0CopyLineage()
        raw=bytearray(vram())
        probe={
            "status":"MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW",
            "first_uv_texture_word_x_words":0,"first_uv_texture_word_y":0,
            "first_uv_clut_row_x_words":32,"first_uv_clut_row_y":19,
            "first_uv_nibble_within_u16":3,
            "selected_palette_halfword_sha256":"x"*64,
        }
        with self.assertRaisesRegex(ValueError,"differs"):
            inspect_private_clut_row_lineage(
                raw,tracker,array("i",[-1])*(1024*512),0,probe,[])

    def test_invalid_probe_nibble_fails_closed(self):
        tracker=PrivateA0CopyLineage()
        probe={
            "status":"MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW",
            "first_uv_texture_word_x_words":0,"first_uv_texture_word_y":0,
            "first_uv_clut_row_x_words":32,"first_uv_clut_row_y":19,
            "first_uv_nibble_within_u16":4,
            "selected_palette_halfword_sha256":hashlib.sha256(b"\0\0").hexdigest(),
        }
        with self.assertRaisesRegex(ValueError,"nibble"):
            inspect_private_clut_row_lineage(
                vram(),tracker,array("i",[-1])*(1024*512),0,probe,[])

    def test_invalid_row_coordinate_and_bad_reference_rejected(self):
        tracker=PrivateA0CopyLineage()
        probe={
            "status":"MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW",
            "first_uv_texture_word_x_words":0,"first_uv_texture_word_y":0,
            "first_uv_clut_row_x_words":1009,"first_uv_clut_row_y":19,
            "first_uv_nibble_within_u16":3,
            "selected_palette_halfword_sha256":hashlib.sha256(b"\0\0").hexdigest(),
        }
        with self.assertRaisesRegex(ValueError,"location"):
            inspect_private_clut_row_lineage(
                vram(),tracker,array("i",[-1])*(1024*512),0,probe,[])
        with self.assertRaises(ValueError):
            inspect_private_clut_row_lineage(vram(),tracker,
                array("i",[-1])*(1024*512),0,{},[
                  {"candidate_bank_index":True,"candidate_row_index":0}])

    def test_no_payload_data_or_source_color_words_in_report(self):
        report=play(setup_packets())
        text=json.dumps(report)
        for forbidden in ('"original_palette_word_bytes"',
                          '"texture_index_u4"','"source_raw_gp0_words"',
                          '"raw_decoded_source_bytes"'):
            self.assertNotIn(forbidden,text)
        self.assertTrue(palette(report)["interpretation"][
            "no_original_source_vram_palette_or_pixel_words_exported"])

    def test_entrypoint_uses_only_synthetic_original_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            initial=root/"before.bin";initial.write_bytes(vram())
            trace=root/"packets.jsonl";write_trace(trace,setup_packets(),frame=12)
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[stream()]}):
                output=audit_private_gp0_upload_timeline(root/"fake",initial,trace)
            self.assertEqual(palette(output)["status"],
                             "CONDITIONAL_FRESH_CANDIDATE_CLUT_ROW_ORIGIN")

if __name__ == "__main__":
    unittest.main()
