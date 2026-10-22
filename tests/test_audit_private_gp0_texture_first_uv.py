"""Stage439: synthetic 4bpp first UV / texture-window / CLUT evidence tests."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_private_gp0_texture_first_uv import probe_first_uv_4bpp
from audit_private_gp0_upload_timeline import (
    VRAM_BYTES, replay_private_gp0_clut_timeline)
from test_audit_private_gp0_upload_timeline import (
    COLORS, BANK, E6, a0, polygon, vram)

E2_ZERO = [0xe2000000]
E2_NONZERO = [0xe2000001]


def sample_polygon(u=3, v=0, page=0):
    packet = polygon(page=page)
    packet[2] = (packet[2] & 0xffff0000) | (v << 8) | u
    return packet


def texture_packet(*, x=0, y=0, texword=0x3210):
    data = struct.pack("<H", texword)
    return a0(data, x=x, y=y, width=1, height=1)


def replay(packets, *, initial=None, bank=None, max_evidence=20000):
    return replay_private_gp0_clut_timeline(
        vram() if initial is None else initial, packets,
        [BANK] if bank is None else [bank],
        frame=439, max_evidence=max_evidence)


class Stage439FirstUVTests(unittest.TestCase):
    def test_unobserved_texture_window_never_infers_address(self):
        result = replay([E6, a0(COLORS), texture_packet(), sample_polygon()])
        info = result["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertEqual(info["status"],"TEXTURE_WINDOW_STATE_NOT_OBSERVED")
        self.assertNotIn("texture_halfword_sha256",info)

    def test_explicit_e2_zero_produces_one_modeled_word_and_clut_entry(self):
        result = replay([E2_ZERO, E6, a0(COLORS),
                         texture_packet(), sample_polygon()])
        event=result["clut_draw_events"][0]
        info=event["first_uv_texture_probe"]
        self.assertEqual(info["status"],
                         "MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW")
        self.assertEqual((info["first_uv_texture_word_x_words"],
                          info["first_uv_texture_word_y"]),(0,0))
        self.assertEqual((info["first_uv_clut_row_x_words"],
                          info["first_uv_clut_row_y"]),(32,19))
        self.assertEqual(info["texture_halfword_sha256"],
                         hashlib.sha256(struct.pack("<H",0x3210)).hexdigest())
        # For u=3, nibble 3 is 0x3: the fourth CLUT entry.
        self.assertEqual(info["selected_palette_halfword_sha256"],
                         hashlib.sha256(COLORS[6:8]).hexdigest())
        self.assertTrue(info["texture_halfword_explicitly_written_since_last_draw"])
        self.assertTrue(info["selected_clut_halfword_explicitly_written_since_last_draw"])
        self.assertTrue(info["gpu_sampling_and_cache_behavior_unverified"])
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])

    def test_first_declared_uv_pixel_is_not_a_raster_visibility_proof(self):
        event=replay([E2_ZERO,E6,a0(COLORS),
                      texture_packet(),sample_polygon()])["clut_draw_events"][0]
        self.assertTrue(event["first_uv_texture_probe"][
            "declared_uv_may_not_correspond_to_visible_rasterized_pixel"])

    def test_nonzero_texture_window_skips_without_predicting_sample(self):
        result=replay([E2_NONZERO,E6,a0(COLORS),
                       texture_packet(),sample_polygon()])
        info=result["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertEqual(info["status"],"NONZERO_TEXTURE_WINDOW_NOT_MODELED")
        self.assertNotIn("selected_palette_halfword_sha256",info)

    def test_explicit_e2_zero_restores_probe_after_nonzero_window(self):
        report=replay([E2_NONZERO,E2_ZERO,E6,a0(COLORS),
                       texture_packet(),sample_polygon()])
        info=report["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertEqual(info["status"],
                         "MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW")
        self.assertEqual(report["counts"]["E2_TEXTURE_WINDOW_EXPLICIT"],2)

    def test_e2_wrong_length_and_reserved_bits_fail_closed(self):
        for packet in ([0xe2000000,0], [0xe2f00000], [0xe2100000]):
            with self.subTest(packet=packet),self.assertRaisesRegex(ValueError,"GP0 E2"):
                replay([packet])

    def test_texture_word_coordinates_include_page_x_y_and_uv(self):
        # 4bpp page X=64 words; base Y=256; u=11 -> word +2, v=20 -> y=276.
        raw = bytearray(vram())
        off=(276*1024+66)*2
        raw[off:off+2]=struct.pack("<H",0x3210)
        off_pal=(19*1024+32)*2
        raw[off_pal:off_pal+32]=COLORS
        event=replay([E2_ZERO,sample_polygon(u=11,v=20,page=0x11)],
                     initial=bytes(raw))["clut_draw_events"][0]
        info=event["first_uv_texture_probe"]
        self.assertEqual((info["first_uv_texture_word_x_words"],
                          info["first_uv_texture_word_y"]),(66,276))
        self.assertEqual(info["selected_palette_halfword_sha256"],
                         hashlib.sha256(COLORS[6:8]).hexdigest())
        self.assertFalse(info["texture_halfword_explicitly_written_since_last_draw"])
        self.assertFalse(info["selected_clut_halfword_explicitly_written_since_last_draw"])

    def test_four_nibble_offsets_select_individual_clut_entries(self):
        for u in range(4):
            with self.subTest(u=u):
                info=replay([E2_ZERO,E6,a0(COLORS),texture_packet(),
                             sample_polygon(u=u)])["clut_draw_events"][0][
                             "first_uv_texture_probe"]
                self.assertEqual(info["selected_palette_halfword_sha256"],
                                 hashlib.sha256(COLORS[2*u:2*u+2]).hexdigest())
                self.assertEqual(info["first_uv_zero_index_hypothesis"],u==0)

    def test_texture_word_recent_but_clut_row_only_in_baseline(self):
        initial=vram(x=32,y=19)
        info=replay([E2_ZERO,E6,texture_packet(),sample_polygon()],
                    initial=initial)["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertTrue(info["texture_halfword_explicitly_written_since_last_draw"])
        self.assertFalse(info["selected_clut_halfword_explicitly_written_since_last_draw"])

    def test_texture_word_upload_stale_after_previous_draw(self):
        report=replay([E2_ZERO,E6,a0(COLORS),texture_packet(),
                       sample_polygon(),sample_polygon()])
        first,second=[e["first_uv_texture_probe"] for e in report["clut_draw_events"]]
        self.assertTrue(first["texture_halfword_explicitly_written_since_last_draw"])
        self.assertFalse(second["texture_halfword_explicitly_written_since_last_draw"])
        self.assertFalse(second["selected_clut_halfword_explicitly_written_since_last_draw"])

    def test_new_texture_and_palette_upload_after_draw_restores_freshness(self):
        report=replay([E2_ZERO,E6,a0(COLORS),texture_packet(),
                       sample_polygon(),a0(COLORS),texture_packet(),sample_polygon()])
        for e in report["clut_draw_events"]:
            info=e["first_uv_texture_probe"]
            self.assertTrue(info["texture_halfword_explicitly_written_since_last_draw"])
            self.assertTrue(info["selected_clut_halfword_explicitly_written_since_last_draw"])

    def test_zero_index_not_assumed_transparent_or_black(self):
        info=replay([E2_ZERO,E6,a0(COLORS),
                     texture_packet(),sample_polygon(u=0)])[
                     "clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertTrue(info["first_uv_zero_index_hypothesis"])
        self.assertNotIn("transparent",json.dumps(info))
        self.assertNotIn("black",json.dumps(info))

    def test_e2_can_follow_E6_without_changing_mask_state(self):
        info=replay([E6,E2_ZERO,a0(COLORS),
                     texture_packet(),sample_polygon()])[
                     "clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertEqual(info["status"],
                         "MODELED_FIRST_DECLARED_UV_WITH_DISABLED_TEXTURE_WINDOW")

    def test_texture_window_state_does_not_turn_8bpp_page_into_4bpp(self):
        report=replay([E2_ZERO,sample_polygon(page=0x80)])
        self.assertEqual(report["clut_draw_events"],[])
        self.assertEqual(report["counts"]["TEXTURED_NOT_4BPP"],1)

    def test_reference_reports_hashes_not_source_color_or_texture_word(self):
        report=replay([E2_ZERO,E6,a0(COLORS),texture_packet(),sample_polygon()])
        encoded=json.dumps(report)
        for forbidden in ('"texture_halfword_raw"','"selected_color_word"',
                          '"raw_4bpp_index"','"original_texture_bytes"',
                          '"palette_u16_values"'):
            self.assertNotIn(forbidden,encoded)
        info=report["clut_draw_events"][0]["first_uv_texture_probe"]
        self.assertTrue(info["no_raw_texture_index_color_or_halfword_exported"])

    def test_model_rejects_invalid_probe_inputs(self):
        from array import array
        px=array("i",[-1])*(1024*512)
        for memory in (b"",bytes(VRAM_BYTES-2)):
            with self.assertRaises(ValueError):
                probe_first_uv_4bpp(memory,px,0,{"tpage":0,"clut":0,"u":0,"v":0},0)
        with self.assertRaises(ValueError):
            probe_first_uv_4bpp(vram(),px,True,{"tpage":0,"clut":0,"u":0,"v":0},0)
        with self.assertRaises(ValueError):
            probe_first_uv_4bpp(vram(),px,0,{"tpage":0,"clut":0,"u":256,"v":0},0)

    def test_existing_stage438_reconciliation_still_works_with_e2_probe(self):
        empty=bytes(VRAM_BYTES)
        report=replay_private_gp0_clut_timeline(
            empty,[E2_ZERO,E6,texture_packet()], [BANK],
            observed_post_vram=(struct.pack("<H",0x3210)+empty[2:]),
            require_post_match=True)
        self.assertTrue(report["postframe_reconciliation"]["all_comparable_words_match"])


if __name__=="__main__":
    unittest.main()
