"""Original-free tests for PS1 Surf Village palette-row diagnostics."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from audit_surf_palette_rows import (  # noqa: E402
    audit_palette_candidates, read_private_candidates,
    bgr555_candidate_rgb, unpack_candidate_4bpp,
)
from export_surf_palette_candidates import fit_aspect  # noqa: E402

RECORD = 0x6000
GRAPHICS = 0x200
GFX_BASE = 0x80164000


def zero_lzss(count):
    tokens=[bytes((0,15))]*(count//18)
    if count%18:
        tokens.append(bytes((0, count%18-3)))
    stream=bytearray(struct.pack("<I",count))
    for i in range(0,len(tokens),8):
        stream.append(0)
        stream.extend(b"".join(tokens[i:i+8]))
    return bytes(stream)


def map_record(index, *, palette_banks=2, corrupt=False,
               invalid_index=False, unaligned_first=False):
    buf=bytearray(RECORD)
    if index==1:
        buf[:7]=b"DUMMY!!"
        return bytes(buf)
    compressed=[zero_lzss(32768),zero_lzss(65536)]
    if corrupt:
        compressed[1]=compressed[1][:100]
    first_len=int(palette_banks*512)+(1 if unaligned_first else 0)
    first_end=0x100+first_len
    # intermediate filler region and two bounded genuine WA1 streams.
    positions=[0x100,first_end,first_end+32]
    for data in compressed:
        positions.append(positions[-1]+len(data)+(-len(data))%4)
    if positions[-1]+4>=RECORD-GRAPHICS:
        raise ValueError("bad test fixture capacity")
    for i,pos in enumerate(positions):
        struct.pack_into("<I",buf,GRAPHICS+i*4,GFX_BASE+pos)
    # The final incomplete item is excluded by the decoder.
    for bank in range(int(palette_banks)):
        for row in range(16):
            if row == 15:
                colors=(0,)*16
            elif row == 0:
                colors=(0,0x001F,0x03E0,0x7C00)+(0x7FFF,)*12
            else:
                colors=(0,)+(0x8000+row+bank,)*15
            struct.pack_into("<16H",buf,GRAPHICS+0x100+
                             bank*512+row*32,*colors)
    for i,data in enumerate(compressed):
        beg=GRAPHICS+positions[2+i]
        buf[beg:beg+len(data)]=data
    if invalid_index:
        struct.pack_into("<I",buf,GRAPHICS,0xF0000000)
    return bytes(buf)


def inspect(m0,m2):
    with tempfile.TemporaryDirectory() as root:
        path=Path(root)/"CDSTG_synthetic.bin"
        path.write_bytes(m0+map_record(1)+m2)
        return audit_palette_candidates(
            path,map_index=2,map_count=3,
            map_bytes=RECORD,graphics_offset=GRAPHICS,dummy_index=1)


class SurfPaletteCandidateTests(unittest.TestCase):
    def test_two_banks_two_valid_wa1_streams(self):
        report=inspect(map_record(0),map_record(2))
        self.assertEqual(report["candidate_512_byte_bank_count"],2)
        self.assertEqual(report["verified_bounded_lzss_stream_count"],2)
        self.assertTrue(report["same_bank_and_stream_count"])
        self.assertEqual(report["candidate_16_color_row_count"],32)
        self.assertEqual(report["all_zero_candidate_row_count"],2)
        self.assertEqual(report["verified_streams"][0]["graphics_region_index"],2)
        self.assertEqual(report["verified_streams"][1]["decoded_bytes"],65536)
        self.assertTrue(report["interpretation"]["choice_among_sixteen_rows_is_unverified"])
        self.assertTrue(report["interpretation"]["no_original_palette_words_or_pixel_bytes_emitted"])

    def test_paletted_rows_are_reported_by_hash_and_counts_only(self):
        report=inspect(map_record(0),map_record(2))
        first=report["candidate_banks"][0]["candidate_16_color_rows"][0]
        self.assertEqual(first["unique_u16_count"],5)
        self.assertEqual(first["zero_u16_count"],1)
        self.assertEqual(first["high_bit_set_u16_count"],0)
        self.assertEqual(len(first["candidate_row_sha256"]),64)
        self.assertNotIn("raw_palette",first)
        self.assertNotIn("decoded_pixels",report)

    def test_truncated_marker_stream_excluded_without_padding(self):
        report=inspect(map_record(0),map_record(2,corrupt=True))
        self.assertEqual(report["candidate_512_byte_bank_count"],2)
        self.assertEqual(report["verified_bounded_lzss_stream_count"],1)
        self.assertFalse(report["same_bank_and_stream_count"])

    def test_palette_bank_mismatch_does_not_prove_corruption(self):
        report=inspect(map_record(0),map_record(2,palette_banks=3))
        self.assertEqual(report["candidate_512_byte_bank_count"],3)
        self.assertEqual(report["verified_bounded_lzss_stream_count"],2)
        self.assertFalse(report["same_bank_and_stream_count"])

    def test_unaligned_candidate_bank_region_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"512-byte aligned"):
            inspect(map_record(0),map_record(2,unaligned_first=True))

    def test_invalid_original_pointer_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"graphics pointer run"):
            inspect(map_record(0),map_record(2,invalid_index=True))

    def test_invalid_file_size_and_dummy_index_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"fake"
            path.write_bytes(map_record(0)+map_record(1)+map_record(2))
            with self.assertRaisesRegex(ValueError,"dummy"):
                read_private_candidates(path,map_index=1,map_count=3,
                                        map_bytes=RECORD,
                                        graphics_offset=GRAPHICS,dummy_index=1)
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError,"length"):
                read_private_candidates(path,map_index=2,map_count=3,
                                        map_bytes=RECORD,
                                        graphics_offset=GRAPHICS,dummy_index=1)

    def test_low_nibble_first_and_bgr555_channel_order(self):
        self.assertEqual(unpack_candidate_4bpp(bytes((0x21,0xF0,0xAB))),
                         bytes((1,2,0,15,11,10)))
        self.assertEqual(bgr555_candidate_rgb(0x001F),(255,0,0))
        self.assertEqual(bgr555_candidate_rgb(0x03E0),(0,255,0))
        self.assertEqual(bgr555_candidate_rgb(0x7C00),(0,0,255))
        self.assertEqual(bgr555_candidate_rgb(0x8000),(0,0,0))
        with self.assertRaises(ValueError):
            bgr555_candidate_rgb(-1)

    def test_preserve_2_to_1_aspect_in_private_contact_sheets(self):
        self.assertEqual(fit_aspect(512,256,245,216),(245,122))
        self.assertEqual(fit_aspect(256,256,245,216),(216,216))
        self.assertEqual(fit_aspect(128,128,256,256),(128,128))
        with self.assertRaises(ValueError):
            fit_aspect(0,256,245,216)

    def test_hypothetical_palette_rows_cannot_prove_original_scene(self):
        report=inspect(map_record(0),map_record(2))
        flags=report["interpretation"]
        self.assertTrue(flags["matching_bank_and_stream_ordinal_is_unverified"])
        self.assertTrue(flags["ps1_stp_bit_and_alpha_are_unverified"])
        self.assertTrue(flags["no_verified_original_ps1_frame_match"])


if __name__=="__main__":
    unittest.main()
