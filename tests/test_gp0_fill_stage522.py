"""Stage522 synthetic GP0(02) bounds, packetization, VRAM replay and origin tests.

All pixels and packets in this test file are artificial; no original ROM,
original capture, game screenshot, or private control hash is committed.
"""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from decode_private_gp0_fill import decode_bounded_gp0_fill
from package_private_raw_gp0_wordstream import packetize_owner_raw_words
from audit_private_gp0_upload_timeline import (
    replay_private_gp0_clut_timeline,VRAM_BYTES,
)
from audit_surf_gp0_clut_references import decode_packet
from test_import_private_pcsx_native_gpudump import (
    base_records,read_native_gpu_dump,select_first_native_gp0_frame,
    dump_bytes,GP0,
)
from test_audit_private_a0_transitive_copy_lineage import (
    play,transitive,direct,copy,draw,upload,E2_ZERO,E6,
)


def fill(color=0x02ffffff,*,x=0,y=0,width=16,height=1):
    return [color,(y<<16)|x,(height<<16)|width]


def words(*packets):
    sequence=[v for packet in packets for v in packet]
    return struct.pack("<%dI"%len(sequence),*sequence)


class Stage522FillTests(unittest.TestCase):
    def test_fill_color_24bit_rgb_to_rgb555_bit15_zero(self):
        for color,expected in (
                (0x02000000,0),(0x020000ff,31),
                (0x0200ff00,992),(0x02ff0000,31744),
                (0x02ffffff,32767),(0x027f7f7f,0x3def)):
            with self.subTest(color=color):
                self.assertEqual(decode_bounded_gp0_fill(fill(color))["pixel"],
                                 expected)

    def test_geometry_x_rounds_down_and_width_up(self):
        g=decode_bounded_gp0_fill(fill(x=47,y=14,width=17,height=3))
        self.assertEqual((g["x"],g["y"],g["width"],g["height"]),
                         (32,14,32,3))

    def test_full_width_rounding_and_last_supported_row(self):
        g=decode_bounded_gp0_fill(fill(x=0,y=1,width=1023,height=511))
        self.assertEqual((g["width"],g["height"]), (1024,511))

    def test_masked_zero_dimensions_are_actual_noop(self):
        for width,height in ((0,1),(31,0),(0,0)):
            with self.subTest(width=width,height=height):
                decoded=decode_bounded_gp0_fill(
                    fill(x=0,y=511,width=width,height=height))
                self.assertEqual(decoded["width"]*decoded["height"],0)

    def test_wrapping_and_reserved_geometry_fail_closed(self):
        for packet in (
                fill(x=1008,width=17),
                fill(y=511,width=16,height=2),
                fill(x=16,width=1023),
                fill(x=0x400),
                fill(y=0x200),
                fill(width=0x400),
                fill(height=0x200),
        ):
            with self.subTest(packet=packet):
                with self.assertRaisesRegex(ValueError,
                        "wraps|reserved"):
                    decode_bounded_gp0_fill(packet)

    def test_incomplete_or_noninteger_fill_rejected(self):
        for packet in ([],[0x02000000],[0x02000000,0],
                       [0x02000000,0,0,0],
                       [0x02000000,0,0.0],
                       [0x02000000,0,True],
                       [0x03000000,0,0]):
            with self.subTest(packet=packet):
                with self.assertRaises(ValueError):
                    decode_bounded_gp0_fill(packet)

    def test_packetizer_retains_exact_gp0_02_three_word_packet(self):
        first=fill(0x02ff001f,x=35,y=2,width=17,height=7)
        tail=[0xe6000000]
        packets,counts=packetize_owner_raw_words(words(first,tail))
        self.assertEqual(packets,[first,tail])
        self.assertEqual(counts["02_FILL"],1)
        self.assertEqual(counts["OTHER_SUPPORTED"],1)
        self.assertEqual(decode_packet(first,None)[0],"VRAM_FILL_RECTANGLE")

    def test_fill_works_without_e6_and_post_vram_exact(self):
        packet=fill(0x0200ff00,x=5,y=7,width=1,height=2)
        expected=bytearray(VRAM_BYTES)
        for y in (7,8):
            expected[(y*1024)*2:(y*1024+16)*2]=struct.pack("<H",992)*16
        result=replay_private_gp0_clut_timeline(
            bytes(VRAM_BYTES),[packet],[],
            observed_post_vram=bytes(expected),require_post_match=True)
        status=result["postframe_reconciliation"]
        self.assertEqual(status["scope"],"ENTIRE_VRAM_NO_GPU_DRAW_PACKETS")
        self.assertEqual(status["known_final_u16_word_count"],1024*512)
        self.assertTrue(status["all_comparable_words_match"])
        self.assertEqual(result["counts"]["02_VRAM_FILL"],1)

    def test_one_pixel_difference_in_reference_is_detected(self):
        reference=bytearray(VRAM_BYTES)
        reference[0:2]=b"\\x00\\x40"
        with self.assertRaisesRegex(ValueError,"postframe reconciliation"):
            replay_private_gp0_clut_timeline(
                bytes(VRAM_BYTES),[fill(width=16,height=1)],[],
                observed_post_vram=bytes(reference),require_post_match=True)

    def test_noop_preserves_unmodified_vram(self):
        out=replay_private_gp0_clut_timeline(
            bytes(VRAM_BYTES),[fill(width=0,height=5)],[],
            observed_post_vram=bytes(VRAM_BYTES),require_post_match=True)
        self.assertEqual(out["counts"]["02_ZERO_DIMENSION_NOOP"],1)

    def test_fill_discards_old_a0_origin_before_texture_draw(self):
        output=play([E2_ZERO,E6,upload(),copy(),
                     fill(x=256,y=0,width=96,height=1),draw()])
        self.assertEqual(transitive(output)["status"],
                         "NO_KNOWN_A0_ORIGIN_FOR_FIRST_UV")
        self.assertEqual(direct(output)["status"],
                         "NO_DIRECT_A0_WRITER_FOR_TEXTURE_WORD")

    def test_synthetic_native_first_frame_imports_with_fill(self):
        records=base_records()
        # A complete synthetic fill is a separate native GP0 transport record.
        records.insert(-1,(GP0,fill(0x0200ff00,x=0,y=0,width=640,height=480)))
        selected=select_first_native_gp0_frame(
            read_native_gpu_dump(dump_bytes(records)))
        self.assertEqual(selected["modeled_packet_counts"]["02_FILL"],1)
        self.assertIn("02_FILL",selected["modeled_packet_counts"])


if __name__=="__main__":
    unittest.main()
