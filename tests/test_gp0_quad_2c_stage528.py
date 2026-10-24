"""Stage528: ROM-free bounded opaque GP0(2C) 4bpp quad regressions."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from replay_private_gp0_quad_2c import replay_bounded_4bpp_quad
from replay_private_gp0_intro_8bpp import replay_bounded_8bpp_intro

W,H=1024,512
SIZE=W*H*2


def word(vram,x,y):
    return struct.unpack_from("<H",vram,2*(y*W+x))[0]


def uv(u,v):
    return ((v&255)<<8)|(u&255)


def packet(*,x=64,y=156,width=4,height=2,u=0,v=0,
           tpage=0x2c,clut=481<<6,tint=0x808080):
    return [0x2c000000|tint,(y<<16)|x,uv(u,v)|(clut<<16),
            (y<<16)|(x+width),uv(u+width-1,v)|(tpage<<16),
            ((y+height)<<16)|x,uv(u,v+height-1),
            ((y+height)<<16)|(x+width),uv(u+width-1,v+height-1)]


def fixture():
    vram=bytearray(SIZE)
    # Totally synthetic 4bpp page at x=768 and 16-color CLUT at y=481.
    struct.pack_into("<H",vram,2*768,0x3210)
    struct.pack_into("<H",vram,2*(W+768),0x7654)
    for i,color in enumerate((0,31,992,31744,32799,1023,32736,32767)):
        struct.pack_into("<H",vram,2*(481*W+i),color)
    return vram


def replay(p=None,*,vram=None,area=(64,122,703,283),**kw):
    data=fixture() if vram is None else vram
    changed=replay_bounded_4bpp_quad(
        data,packet() if p is None else p,draw_area=area,**kw)
    return data,changed


class Stage528QuadTests(unittest.TestCase):
    def test_four_nibbles_two_rows_and_exact_clut(self):
        data,writes=replay()
        self.assertEqual(writes,7)
        self.assertEqual([word(data,64+x,156) for x in range(4)],
                         [0,31,992,31744])
        self.assertEqual([word(data,64+x,157) for x in range(4)],
                         [32799,1023,32736,32767])

    def test_index_zero_can_resolve_to_nonzero_color(self):
        data=fixture()
        struct.pack_into("<H",data,2*(481*W),31)
        out,writes=replay(vram=data)
        self.assertEqual(word(out,64,156),31)
        self.assertEqual(writes,8)

    def test_stp_does_not_blend_opaque_2c(self):
        data=fixture()
        struct.pack_into("<H",data,2*(157*W+64),32767)
        out,_=replay(vram=data)
        self.assertEqual(word(out,64,157),32799)

    def test_rgb555_modulation_per_channel(self):
        out,_=replay(packet(tint=0x404040))
        self.assertEqual([word(out,65+x,156) for x in range(3)],
                         [15,15<<5,15<<10])

    def test_clip_preserves_uv_sampling_coordinates(self):
        out,writes=replay(area=(66,157,67,157))
        self.assertEqual(writes,2)
        self.assertEqual([word(out,x,157) for x in (64,65,66,67)],
                         [0,0,32736,32767])

    def test_wrapped_synthetic_u_coordinates_resolve_nibbles(self):
        data=bytearray(SIZE)
        struct.pack_into("<H",data,2*(768+63),0x1000)
        struct.pack_into("<H",data,2*768,1)
        struct.pack_into("<H",data,2*(481*W+1),992)
        out,writes=replay(packet(u=255,width=2,height=1),vram=data)
        self.assertEqual(writes,2)
        self.assertEqual([word(out,x,156) for x in (64,65)],[992,992])

    def test_nonrectangular_and_noncanonical_uv_fail_closed(self):
        cases=[]
        a=packet();a[7]+=1;cases.append(a)
        for i in (4,6,8):
            a=packet();a[i]^=1;cases.append(a)
        for p in cases:
            with self.subTest(packet_index=p[0]),self.assertRaises(ValueError):
                replay(p)

    def test_reserved_fields_malformed_packet_and_modes_fail_closed(self):
        bad=[packet()[:-1],[0x2e808080]+packet()[1:],
             packet(tpage=0xac),packet(tpage=0xcc),packet(tpage=0x0c)]
        for i in (6,8):
            a=packet();a[i]|=0x10000;bad.append(a)
        for p in bad:
            with self.subTest(size=len(p)),self.assertRaises(ValueError):
                replay(p)

    def test_mask_window_offset_clip_and_alias_rejected(self):
        for kw in ({"mask":1},{"offset":1},{"texture_window":1}):
            with self.subTest(kwargs=kw),self.assertRaises(ValueError):
                replay(**kw)
        for p in (packet(x=768,y=0),packet(x=0,y=481),
                  packet(x=1023),packet(width=257),packet(y=511,height=2)):
            with self.assertRaises(ValueError):
                replay(p)

    def test_full_stage528_parser_integration_uses_polygon_tpage(self):
        # All packets/pixels synthetic; GP0(2C) derives its own page from
        # second vertex UV, rather than inheriting E1 page from sprites.
        commands=[[0xe3000000],[0xe407ffff],[0xe5000000],
                  [0xe100002a],[0xe2000000],[0xe6000000]]
        pre=bytes(fixture())
        out,summary=replay_bounded_8bpp_intro(pre,commands+[packet()])
        self.assertEqual(word(out,65,156),31)
        self.assertEqual(summary["counts"]["2C_BOUNDED_OPAQUE_4BPP_QUAD"],1)

    def test_new_noncanonical_quad_does_not_invalidate_sony_8bpp(self):
        from test_replay_private_gp0_intro_8bpp import fixture as old_vram,state,rect
        pre=old_vram(first=0x801f,second=0x03e0)
        out,summary=replay_bounded_8bpp_intro(pre,state()+[rect()])
        self.assertEqual(word(out,4,8),0x8006)
        self.assertEqual(summary["counts"]["66_TEXTURED_SEMITRANSPARENT_RECT"],1)


if __name__=="__main__":
    unittest.main()
