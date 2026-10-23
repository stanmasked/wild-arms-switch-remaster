"""Stage513: synthetic nonzero-origin/row-stride Player V2 PNG+VRAM witness tests.

No original Wild Arms bytes, screenshots, or private SHA-256 values are used.
"""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_verify_private_pcsx_native_gpudump_import import prepared
from test_verify_private_gpudump_player_step1_dump_hash import container
from verify_private_gpudump_player_step1_dump_hash import (
    verify_private_dump_hash_bound_step1_export,
)

X,Y,W,H=211,37,3,2
PIXELS=(0x001f,0x03e0,0x7c00,0x7fff,0x4210,0x801f)


def chunk(kind,payload):
    return (struct.pack(">I",len(payload))+kind+payload+
            struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff))


def rgb(word):
    return bytes(((word&31)<<3,((word>>5)&31)<<3,((word>>10)&31)<<3))


def image(rows):
    h=len(rows)
    w=len(rows[0])
    header=struct.pack(">IIBBBBB",w,h,8,2,0,0,0)
    lines=b"".join(bytes([0])+b"".join(rgb(p) for p in row) for row in rows)
    return (bytes((137,80,78,71,13,10,26,10))+
            chunk(b"IHDR",header)+chunk(b"IDAT",zlib.compress(lines))+
            chunk(b"IEND",b""))


def synthetic_pair(root):
    root=Path(root)
    native,before,trace=prepared(root)
    after=bytearray(before.read_bytes())
    for i,word in enumerate(PIXELS):
        row,col=divmod(i,W)
        offset=((Y+row)*1024+X+col)*2
        after[offset:offset+2]=word.to_bytes(2,"little")
    snapshot=root/"frame1.v2.bin"
    snapshot.write_bytes(container(bytes(after),hashlib.sha256(native.read_bytes()).digest()))
    screenshot=root/"frame1.png"
    screenshot.write_bytes(image((PIXELS[:W],PIXELS[W:])))
    return native,before,trace,snapshot,screenshot


def audit(paths,**kwargs):
    return verify_private_dump_hash_bound_step1_export(
        *paths,x=X,y=Y,width=W,height=H,**kwargs)


class OffsetRoiTests(unittest.TestCase):
    def test_true_nonzero_origin_matches_across_vram_rows(self):
        with tempfile.TemporaryDirectory() as root:
            report=audit(synthetic_pair(root),require_changed_roi=True)
            self.assertTrue(report["roi_exact_rgb_equal"])
            self.assertEqual(report["roi_compared_pixel_count"],6)
            self.assertEqual(report["roi_mismatched_pixel_count"],0)
            self.assertTrue(report["exported_vram_crc32_verified"])

    def test_wrong_vram_x_or_y_fails_even_if_png_dimensions_match(self):
        with tempfile.TemporaryDirectory() as root:
            paths=synthetic_pair(root)
            for x,y in ((X+1,Y),(X,Y+1),(0,0)):
                with self.subTest(x=x,y=y),self.assertRaisesRegex(
                        ValueError,"PNG RGB differs"):
                    verify_private_dump_hash_bound_step1_export(
                        *paths,x=x,y=y,width=W,height=H)

    def test_swapped_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            paths=synthetic_pair(root)
            paths[-1].write_bytes(image((PIXELS[W:],PIXELS[:W])))
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                audit(paths)

    def test_reversed_pixels_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            paths=synthetic_pair(root)
            paths[-1].write_bytes(image((
                tuple(reversed(PIXELS[:W])),
                tuple(reversed(PIXELS[W:])),
            )))
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                audit(paths)

    def test_scaled_or_padded_roi_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            paths=synthetic_pair(root)
            with self.assertRaisesRegex(ValueError,"exact unscaled ROI"):
                verify_private_dump_hash_bound_step1_export(
                    *paths,x=X,y=Y,width=W+1,height=H)


if __name__=="__main__":
    unittest.main()
