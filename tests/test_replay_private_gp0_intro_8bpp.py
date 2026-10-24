"""ROM-free Stage524 bounded GP0(66) 8bpp CLUT + RGB555 replay tests."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from replay_private_gp0_intro_8bpp import (
    VRAM_BYTES, replay_bounded_8bpp_intro,
)


def state():
    return [[0xe3000000], [0xe407ffff], [0xe5000000],
            [0xe10000aa], [0xe2000000], [0xe6000000]]


def rect(*, x=4, y=8, u=0, v=0, width=2, height=1,
         tint=0x1a1a1a, clut_y=480):
    return [0x66000000 | tint, y << 16 | x,
            ((clut_y << 6) << 16) | (v << 8) | u,
            height << 16 | width]


def fixture(*, first=0x8000001f, second=0x00007fff, texture=0x0201,
            background=0, x=4, y=8):
    vram = bytearray(VRAM_BYTES)
    # E1 page X=640, depth=8bpp; two indexed texels per u16 word.
    struct.pack_into("<H", vram, (0*1024 + 640)*2, texture)
    struct.pack_into("<H", vram, (480*1024 + 1)*2, first & 0xffff)
    struct.pack_into("<H", vram, (480*1024 + 2)*2, second & 0xffff)
    struct.pack_into("<H", vram, (y*1024 + x)*2, background)
    return bytes(vram)


def pixel(vram, x=4, y=8):
    return struct.unpack_from("<H", vram, (y*1024+x)*2)[0]


class Stage524IndexedIntroTests(unittest.TestCase):
    def test_indexed_8bpp_both_bytes_select_distinct_palette_entries(self):
        pre=fixture(first=0x801f, second=0x03e0)
        out, stats=replay_bounded_8bpp_intro(pre, state()+[rect()])
        # palette1 red=31 => floor(31*26/128)=6 + bit15.
        self.assertEqual(pixel(out),0x8006)
        # palette2 green=31 => floor(31*26/128)=6, no bit15.
        self.assertEqual(pixel(out,5,8),0x00c0)
        self.assertEqual(stats["counts"]["66_TEXTURED_SEMITRANSPARENT_RECT"],1)

    def test_fill_then_sprite_clear_and_redraw_in_packet_order(self):
        pre=fixture(first=0x801f, second=0x03e0,
                    background=0x7fff)
        packet=[0x02000000,0,0x00100010]  # 16x16 black fill
        out, stats=replay_bounded_8bpp_intro(pre, state()+[packet,rect()])
        self.assertEqual(pixel(out),0x8006)
        self.assertEqual(pixel(out,5,8),0x00c0)
        self.assertEqual(pixel(out,4,9),0)
        self.assertEqual(stats["counts"]["02_BOUNDED_FILL"],1)

    def test_additive_blend_from_texel_mask_bit15(self):
        old=(20 << 10) | (15 << 5) | 28
        pre=fixture(first=0x801f,background=old)
        out,_=replay_bounded_8bpp_intro(pre,state()+[rect(width=1)])
        # STP=1, ABR=1 -> saturated per-channel B+F.
        self.assertEqual(pixel(out),0x8000 | (20 << 10) | (15 << 5) | 31)

    def test_opaque_texel_overwrites_background_even_under_abe(self):
        pre=fixture(first=0x001f,background=0x7fff)
        out,_=replay_bounded_8bpp_intro(pre,state()+[rect(width=1)])
        self.assertEqual(pixel(out),6)

    def test_paletted_black_8000_is_not_transparent(self):
        pre=fixture(first=0x8000,background=0x7fff)
        out,_=replay_bounded_8bpp_intro(pre,state()+[rect(width=1)])
        self.assertEqual(pixel(out),0xffff)

    def test_zero_texel_is_fully_transparent(self):
        pre=fixture(first=0,background=0x1234)
        out,_=replay_bounded_8bpp_intro(pre,state()+[rect(width=1)])
        self.assertEqual(pixel(out),0x1234)

    def test_draw_area_clips_exactly_without_overwriting_adjacent(self):
        pre=fixture(first=0x801f, second=0x03e0)
        commands=state()
        commands[1]=[0xe4002004] # E4 inclusive X=4 Y=8
        out,_=replay_bounded_8bpp_intro(pre,commands+[rect()])
        self.assertEqual(pixel(out,4,8),0x8006)
        self.assertEqual(pixel(out,5,8),0)

    def test_color_tint_is_5bit_palette_times_8bit_command_over_128(self):
        pre=fixture(first=0xffff,second=0xffff)
        out,_=replay_bounded_8bpp_intro(
            pre,state()+[rect(tint=0x000080c0)])
        # B=0 =>0; G=128 =>31; R=192 => saturated31.
        self.assertEqual(pixel(out),0x8000 | 31 | (31 << 5))

    def test_without_explicit_state_refuses_to_guess(self):
        with self.assertRaisesRegex(ValueError,"complete explicit GPU state"):
            replay_bounded_8bpp_intro(fixture(),[rect()])

    def test_unsupported_e1_depth_or_blending_refused(self):
        for e1 in (0xe100002a,0xe100012a,0xe100004a):
            states=state()
            states[3]=[e1]
            with self.subTest(e1=e1), self.assertRaisesRegex(ValueError,
                    "requires 8bpp/ABR1"):
                replay_bounded_8bpp_intro(fixture(),states+[rect()])

    def test_nonzero_texture_window_or_mask_or_offset_refused(self):
        for index,cmd in ((4,0xe2000001),(5,0xe6000001),
                          (2,0xe5000001)):
            states=state();states[index]=[cmd]
            with self.subTest(cmd=cmd),self.assertRaisesRegex(ValueError,
                    "requires 8bpp/ABR1"):
                replay_bounded_8bpp_intro(fixture(),states+[rect()])

    def test_unknown_polygon_or_gp0_01_refused(self):
        for bad in ([0x20000000],[0x01000000],[0x40000000],
                    [0x66000000,0,0]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replay_bounded_8bpp_intro(fixture(),state()+[bad])

    def test_unsupported_geometry_texture_alias_and_clut_bit15_refused(self):
        invalid=[
            rect(x=1023,width=16),
            rect(x=700,width=8),
            rect(clut_y=480)[:2]+[0xf8000000,0x00010001],
            rect(x=4,y=8,width=1023),
        ]
        for packet in invalid:
            with self.subTest(packet=packet),self.assertRaises(ValueError):
                replay_bounded_8bpp_intro(fixture(),state()+[packet])

    def test_empty_sprite_and_canonical_nops_do_not_touch_vram(self):
        pre=fixture()
        out,stats=replay_bounded_8bpp_intro(
            pre,state()+[[0],rect(width=0),[0]])
        self.assertEqual(out,pre)
        self.assertEqual(stats["counts"]["00_NOP"],2)
        self.assertEqual(stats["counts"]["66_EMPTY_RECT"],1)

    def test_complete_synthetic_native_gpu_frame_import_and_rgb_replay(self):
        # Exercise the real upstream native-import/GP0-packetizer interface,
        # not just the rectangle function in isolation. All data synthetic.
        from test_import_private_pcsx_native_gpudump import (
            MAGIC, native_record, GPU_VERSION, GP0, GP1, TRACE_BEGIN,
            VSYNC, read_native_gpu_dump, select_first_native_gp0_frame,
        )
        from package_private_raw_gp0_wordstream import packetize_owner_raw_words
        pre=fixture(first=0x801f,second=0x03e0,background=0x7fff)
        full_words=[0xa0000000,0,0x02000400]
        full_words.extend(struct.unpack("<%dI"%(VRAM_BYTES//4),pre))
        restore=[0xe10000aa,0xe2000000,0xe3000000,
                 0xe407ffff,0xe5000000,0xe6000000]
        clear=[0x02000000,0,0x00100010]
        synthetic=MAGIC+b"".join([
            native_record(GPU_VERSION,[2]),
            native_record(GP1,[0]),
            native_record(GP0,full_words),
            native_record(GP0,restore),
            native_record(GP1,[0x03000000,0x08000000]),
            native_record(TRACE_BEGIN),
            native_record(GP1,[0x03000000]),
            native_record(GP0,clear+rect()),
            native_record(VSYNC,[1234,0]),
        ])
        parsed=select_first_native_gp0_frame(
            read_native_gpu_dump(synthetic))
        self.assertEqual(parsed["initial_vram"],pre)
        self.assertEqual(parsed["idempotent_live_gp1_control_word_count"],1)
        gp0_packets,_=packetize_owner_raw_words(parsed["modeled_gp0_raw"])
        output,counters=replay_bounded_8bpp_intro(pre,gp0_packets)
        self.assertEqual(pixel(output),0x8006)
        self.assertEqual(pixel(output,5,8),0x00c0)
        self.assertEqual(pixel(output,4,9),0)
        self.assertEqual(len(output),VRAM_BYTES)
        self.assertEqual(counters["counts"]["02_BOUNDED_FILL"],1)
        self.assertEqual(
            counters["counts"]["66_TEXTURED_SEMITRANSPARENT_RECT"],1)

    def test_next_real_scene_opcode_classes_explicitly_fail_closed(self):
        # Stage525 original-developer-logo capture has GP0(2C) and GP0(64).
        # Synthetic standalone packets only; their rasterization remains
        # unmodeled. Even a fully specified GPU state must not bypass refusal.
        polygon=[0x2c000000]+[0]*8
        rectangle=[0x64000000,0,0,0x00010001]
        for candidate in (polygon,rectangle):
            with self.subTest(opcode=candidate[0]>>24):
                with self.assertRaisesRegex(ValueError,
                        "unsupported GP0 packet size|GPU primitive"):
                    replay_bounded_8bpp_intro(
                        fixture(),state()+[candidate])

    def test_known_intro_command_followed_by_developer_opcode_fails(self):
        # It is not enough to handle the 8bpp splash commands: any
        # subsequent unmodeled draw prevents a complete-frame verdict.
        next_scene=[0x64000000,0,0,0x00010001]
        with self.assertRaisesRegex(ValueError,"GPU primitive"):
            replay_bounded_8bpp_intro(
                fixture(),state()+[rect(),next_scene])

    def test_input_types_and_vram_size_fail_closed(self):
        for bad in (bytes(1),bytearray(VRAM_BYTES),None):
            with self.subTest(type=type(bad)),self.assertRaises(ValueError):
                replay_bounded_8bpp_intro(bad,state())
        with self.assertRaises(ValueError):
            replay_bounded_8bpp_intro(bytes(VRAM_BYTES),[[True]])


if __name__=="__main__":
    unittest.main()
