"""Stage527: ROM-free GP0(64) opaque, 4bpp indexed rectangle regressions.

No copyrighted source/VRAM/CLUT samples or authentic trace words are used.
"""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from replay_private_gp0_intro_8bpp import (
    VRAM_BYTES,replay_bounded_8bpp_intro,
)

WIDTH=1024

def states(page=9,abr=1,depth=0):
    return [[0xe3000000],[0xe407ffff],[0xe5000000],
            [0xe1000000 | page | (abr<<5) | (depth<<7)],
            [0xe2000000],[0xe6000000]]

def four_bpp_texture(vram, indices=0x3210,*,page=9,ty=0):
    struct.pack_into("<H",vram,(ty*WIDTH+page*64)*2,indices)

def palette(vram, entries, *, x=0, y=480):
    for index,pixel in entries.items():
        struct.pack_into("<H",vram,(y*WIDTH+x+index)*2,pixel)

def fixture(indices=0x3210,*,colors=None,background=0):
    mem=bytearray(VRAM_BYTES)
    four_bpp_texture(mem,indices)
    palette(mem,colors if colors is not None else {
        0:0x001f,1:0x03e0,2:0x7c00,3:0x801f})
    for x in range(4,9):
        struct.pack_into("<H",mem,(8*WIDTH+x)*2,background)
    return bytes(mem)

def rect(*,x=4,y=8,u=0,v=0,width=4,height=1,
         tint=0x808080,clut_x=0,clut_y=480):
    clut=((clut_y<<6)|(clut_x//16))
    return [0x64000000|tint,(y<<16)|x,
            (clut<<16)|(v<<8)|u,(height<<16)|width]

def pixel(buf,x=4,y=8):
    return struct.unpack_from("<H",buf,(y*WIDTH+x)*2)[0]

class Stage527FourBitSpriteTests(unittest.TestCase):
    def test_four_packed_nibbles_address_four_distinct_clut_entries(self):
        original=fixture()
        result,stats=replay_bounded_8bpp_intro(
            original,states()+[rect()])
        self.assertEqual([pixel(result,x) for x in (4,5,6,7)],
                         [0x001f,0x03e0,0x7c00,0x801f])
        self.assertEqual(stats["counts"]["64_TEXTURED_OPAQUE_4BPP_RECT"],1)
        self.assertEqual(stats["bounded_pixel_write_count_not_unique_pixels"],4)

    def test_high_stp_bit_is_opaque_without_additive_blend(self):
        original=fixture(indices=0x0003,background=0x7fff)
        result,_=replay_bounded_8bpp_intro(original,states()+[rect(width=1)])
        self.assertEqual(pixel(result),0x801f)

    def test_transparent_zero_rgb555_index_retains_old_pixel(self):
        original=fixture(indices=0x0000,colors={0:0},background=0x4567)
        result,_=replay_bounded_8bpp_intro(original,states()+[rect(width=1)])
        self.assertEqual(pixel(result),0x4567)

    def test_palette_index_zero_not_automatically_transparent(self):
        original=fixture(indices=0x0000,colors={0:0x7c00},background=0)
        result,_=replay_bounded_8bpp_intro(original,states()+[rect(width=1)])
        self.assertEqual(pixel(result),0x7c00)

    def test_rgb_modulation_and_saturation(self):
        original=fixture(indices=0x0000,colors={0:0x7fff})
        result,_=replay_bounded_8bpp_intro(
            original,states()+[rect(width=1,tint=0x000040c0)])
        self.assertEqual(pixel(result),31|(15<<5))

    def test_clut_origin_in_halfword_steps(self):
        mem=bytearray(fixture(indices=0x0001))
        palette(mem,{1:0x001f},x=16)
        result,_=replay_bounded_8bpp_intro(
            bytes(mem),states()+[rect(width=1,clut_x=16)])
        self.assertEqual(pixel(result),0x001f)

    def test_draw_area_clips_without_resampling_uv(self):
        cmds=states()
        cmds[0]=[0xe3002005] # x >=5, y >=8
        result,_=replay_bounded_8bpp_intro(fixture(),cmds+[rect()])
        self.assertEqual(pixel(result,4,8),0)
        self.assertEqual(pixel(result,5,8),0x03e0)

    def test_reject_8bpp_page_for_gp0_64_and_other_modes(self):
        for altered in (0xe10000c9,0xe1000149,0xe1000069):
            cmds=states()
            cmds[3]=[altered]
            with self.subTest(mode=altered):
                with self.assertRaisesRegex(ValueError,"requires 4bpp"):
                    replay_bounded_8bpp_intro(fixture(),cmds+[rect()])

    def test_reject_unknown_mask_window_or_draw_offset(self):
        for i,w in ((4,0xe2000001),(5,0xe6000001),(2,0xe5000001)):
            cmds=states()
            cmds[i]=[w]
            with self.subTest(word=w):
                with self.assertRaisesRegex(ValueError,"requires 4bpp"):
                    replay_bounded_8bpp_intro(fixture(),cmds+[rect()])

    def test_reject_texture_source_overlaps_destination(self):
        cmds=states(page=0)
        with self.assertRaisesRegex(ValueError,"self-modifying"):
            replay_bounded_8bpp_intro(
                fixture(),cmds+[rect(x=8,y=8,width=16,height=1)])

    def test_reject_incomplete_or_unmodeled_geometry(self):
        for bad in (rect()[:3],rect(width=1023),[0x2c808080]+[0]*8):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    replay_bounded_8bpp_intro(fixture(),states()+[bad])

    def test_zero_width_is_noop(self):
        original=fixture()
        result,stats=replay_bounded_8bpp_intro(
            original,states()+[rect(width=0)])
        self.assertEqual(result,original)
        self.assertEqual(stats["counts"]["64_EMPTY_RECT"],1)

    def test_state_change_from_e1_8bpp_to_4bpp_between_rectangles(self):
        # All pixels and CLUT bytes are synthetic, and state transitions
        # must be applied in the precise order of the original GP0 words.
        mem=bytearray(fixture())
        struct.pack_into("<H",mem,(0*WIDTH+640)*2,0x0101)
        first=[[0xe10000aa],
               [0x66000000|0x808080,8<<16|16,(480<<6)<<16,1<<16|1]]
        second=[[0xe1000029],rect(width=1)]
        out,stats=replay_bounded_8bpp_intro(
            bytes(mem),states(page=10,depth=1)+first+second)
        self.assertEqual(pixel(out),0x001f)
        self.assertEqual(stats["counts"]["66_TEXTURED_SEMITRANSPARENT_RECT"],1)
        self.assertEqual(stats["counts"]["64_TEXTURED_OPAQUE_4BPP_RECT"],1)

if __name__=="__main__":
    unittest.main()
