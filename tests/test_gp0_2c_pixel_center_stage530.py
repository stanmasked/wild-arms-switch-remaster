"""Stage530 ROM-free 16.16 GP0(2C) per-pixel interpolation regressions.

No original Wild Arms GPU dump, palette, captured texture or screenshot.
"""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from replay_private_gp0_quad_2c import replay_bounded_4bpp_quad
from replay_private_gp0_intro_8bpp import replay_bounded_8bpp_intro

W,H=1024,512
SIZE=W*H*2
SRC_PAGE_X=768
CLUT_Y=481
BASE_X,BASE_Y=64,156


def u16(buf,x,y): return struct.unpack_from("<H",buf,2*(W*y+x))[0]


def set_u16(buf,x,y,v): struct.pack_into("<H",buf,2*(W*y+x),v)


def synthetic_checker(*,vertical=False):
    out=bytearray(SIZE)
    for index in range(16):
        set_u16(out,index,CLUT_Y,0x1200+index)
    # Packed nibble gradients, independent from destination framebuffer.
    for v in range(128 if vertical else 1):
        for group in range(64 if not vertical else 1):
            word=0
            for nibble in range(4):
                uv=(v if vertical else group*4+nibble)
                word|=(uv & 15) << (4*nibble)
            set_u16(out,SRC_PAGE_X+group,v,word)
    return out


def packet(*,width=256,height=1,u=0,v=0):
    rgb=0x808080
    uv=lambda x,y:(y&255)<<8 | (x&255)
    return [0x2c000000|rgb,(BASE_Y<<16)|BASE_X,
        uv(u,v)|(CLUT_Y<<6)<<16,
        (BASE_Y<<16)|(BASE_X+width),
        uv(u+width-1,v)|(0x2c<<16),
        ((BASE_Y+height)<<16)|BASE_X,uv(u,v+height-1),
        ((BASE_Y+height)<<16)|(BASE_X+width),
        uv(u+width-1,v+height-1)]


class Stage530PixelCenterTests(unittest.TestCase):
    def test_last_pixel_255_is_not_sampled_on_256_cell_polygon(self):
        vram=synthetic_checker()
        writes=replay_bounded_4bpp_quad(
            vram,packet(),draw_area=(64,122,703,283))
        self.assertEqual(writes,256)
        # Width=256, UV vertex separation=255, pixel-centre sampling.
        self.assertEqual(u16(vram,BASE_X+0,BASE_Y),0x1200)
        self.assertEqual(u16(vram,BASE_X+128,BASE_Y),0x1200)
        self.assertEqual(u16(vram,BASE_X+254,BASE_Y),0x120d)
        self.assertEqual(u16(vram,BASE_X+255,BASE_Y),0x120e)
        self.assertEqual(u16(vram,BASE_X+256,BASE_Y),0)

    def test_last_row_127_maps_to_texel_126(self):
        vram=synthetic_checker(vertical=True)
        writes=replay_bounded_4bpp_quad(
            vram,packet(width=1,height=128),draw_area=(64,122,703,283))
        self.assertEqual(writes,128)
        self.assertEqual(u16(vram,BASE_X,BASE_Y+0),0x1200)
        self.assertEqual(u16(vram,BASE_X,BASE_Y+64),0x1200)
        self.assertEqual(u16(vram,BASE_X,BASE_Y+127),0x120e)
        self.assertEqual(u16(vram,BASE_X,BASE_Y+128),0)

    def test_width_four_rounds_pixel_center_not_primitive_uv_end(self):
        vram=synthetic_checker()
        replay_bounded_4bpp_quad(vram,packet(width=4),draw_area=(64,122,703,283))
        self.assertEqual([u16(vram,BASE_X+i,BASE_Y) for i in range(4)],
                         [0x1200,0x1201,0x1202,0x1202])

    def test_small_width_two_reaches_uv_endpoint(self):
        vram=synthetic_checker()
        replay_bounded_4bpp_quad(vram,packet(width=2),draw_area=(64,122,703,283))
        self.assertEqual([u16(vram,BASE_X+i,BASE_Y) for i in range(2)],
                         [0x1200,0x1201])

    def test_flat_gp0_2c_interpolates_same_when_e1_dither_enabled(self):
        baseline=bytes(synthetic_checker())
        def state(dither):
            return [[0xe3000000],[0xe407ffff],[0xe5000000],
                    [0xe100002a|(0x200 if dither else 0)],
                    [0xe2000000],[0xe6000000]]
        a,ca=replay_bounded_8bpp_intro(baseline,state(False)+[packet()])
        b,cb=replay_bounded_8bpp_intro(baseline,state(True)+[packet()])
        self.assertEqual(a,b)
        self.assertEqual(ca["counts"]["2C_BOUNDED_OPAQUE_4BPP_QUAD"],1)
        self.assertEqual(cb["counts"]["2C_BOUNDED_OPAQUE_4BPP_QUAD"],1)

    def test_inverted_noncanonical_uv_still_rejected(self):
        malformed=packet()
        malformed[4]^=1
        with self.assertRaises(ValueError):
            replay_bounded_4bpp_quad(
                synthetic_checker(),malformed,
                draw_area=(64,122,703,283))


if __name__=="__main__":
    unittest.main()
