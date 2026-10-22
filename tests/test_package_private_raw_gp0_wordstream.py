"""Stage446: ROM-free raw little-endian GP0 wordstream packetizer regressions."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from package_private_raw_gp0_wordstream import (
    MAX_RAW_BYTES, packetize_owner_raw_words, package_private_gp0_raw_capture,
)
from audit_private_gp0_upload_timeline import (
    VRAM_BYTES, read_private_gp0_timeline)
from test_audit_private_gp0_upload_timeline import (
    E6, COLORS, BANK, a0, polygon, vram_copy,
)
from test_audit_private_gp0_texture_first_uv import E2_ZERO

def raw(*packets):
    return b"".join(
        struct.pack("<I", word)
        for packet in packets for word in packet
    )

def fixture(directory, words=None):
    directory=Path(directory)
    src=directory/"gpu.raw.u32le"
    initial=directory/"initial.vram.u16le"
    dest=directory/"gpu.timeline.jsonl"
    src.write_bytes(raw(E6, a0(COLORS), polygon()) if words is None else words)
    initial.write_bytes(bytes(VRAM_BYTES))
    return src,initial,dest

class Stage446PacketizerTests(unittest.TestCase):
    def test_roundtrip_a0_and_polygon_preserves_exact_packet_boundaries(self):
        data=raw(E6, E2_ZERO, a0(COLORS), polygon())
        packets,counts=packetize_owner_raw_words(data)
        self.assertEqual(packets,[E6,E2_ZERO,a0(COLORS),polygon()])
        self.assertEqual(counts["A0_UPLOAD"],1)
        self.assertEqual(counts["OTHER_SUPPORTED"],3)

    def test_a0_image_words_that_look_like_opcodes_are_not_commands(self):
        words=[
            0xa0000000,0,0x00010004,
            0xe1000001,0x80000000,
        ]
        packets,counts=packetize_owner_raw_words(raw(E6,words,polygon()))
        self.assertEqual(len(packets),3)
        self.assertEqual(packets[1],words)
        self.assertEqual(counts["A0_UPLOAD"],1)

    def test_odd_pixel_upload_consumes_one_padded_high_halfword(self):
        # Three u16 pixels => two raw GPU u32 image words.
        transfer=[0xa0000000,0,0x00010003,0x22221111,0xe1003333]
        packets,_=packetize_owner_raw_words(raw(E6,transfer,[0x00000000]))
        self.assertEqual(packets,[E6,transfer,[0x00000000]])

    def test_no_a0_data_before_explicit_mask_disabled_state(self):
        with self.assertRaisesRegex(ValueError,"explicit GP0"):
            packetize_owner_raw_words(raw(a0(COLORS)))

    def test_no_80_copy_before_explicit_mask_disabled_state(self):
        with self.assertRaisesRegex(ValueError,"explicit GP0"):
            packetize_owner_raw_words(raw(vram_copy()))

    def test_80_copy_after_disabled_mask_is_supported(self):
        commands=[E6,vram_copy()]
        packets,c=packetize_owner_raw_words(raw(*commands))
        self.assertEqual(packets,commands)
        self.assertEqual(c["80_COPY"],1)

    def test_80_copy_overlapping_source_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"overlapping"):
            packetize_owner_raw_words(raw(E6,vram_copy(dx=40)))

    def test_80_copy_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError,"source/destination"):
            packetize_owner_raw_words(raw(E6,vram_copy(sx=1018,width=16)))

    def test_e6_enabled_mask_rejected(self):
        for command in (0xe6000001,0xe6000002,0xe6000004):
            with self.subTest(command=command), self.assertRaisesRegex(ValueError,"mask"):
                packetize_owner_raw_words(raw([command]))

    def test_e2_texture_window_reserved_bits_rejected(self):
        with self.assertRaisesRegex(ValueError,"reserved bits"):
            packetize_owner_raw_words(raw([0xe2100000]))

    def test_unmodeled_primitive_and_gpu_fill_fail_closed(self):
        for opcode in (0x02000000,0x40000000,0xc0000000):
            with self.subTest(opcode=opcode), self.assertRaisesRegex(ValueError,"unsupported"):
                packetize_owner_raw_words(raw([opcode]))

    def test_incomplete_final_gp0_word_fails(self):
        with self.assertRaisesRegex(ValueError,"incomplete final 32-bit"):
            packetize_owner_raw_words(raw(E6)+b"XYZ")

    def test_incomplete_a0_header_fails(self):
        with self.assertRaisesRegex(ValueError,"truncated GP0 A0 header"):
            packetize_owner_raw_words(raw(E6,[0xa0000000]))

    def test_incomplete_a0_pixel_payload_fails(self):
        p=a0(COLORS)
        with self.assertRaisesRegex(ValueError,"incomplete final GP0 packet"):
            packetize_owner_raw_words(raw(E6,p[:-1]))

    def test_incomplete_polygon_fails(self):
        with self.assertRaisesRegex(ValueError,"incomplete final GP0 packet"):
            packetize_owner_raw_words(raw(polygon()[:-1]))

    def test_bad_a0_rectangle_wrap_fails(self):
        p=a0(COLORS)
        p[1]=(0<<16)|1020
        with self.assertRaisesRegex(ValueError,"bounds"):
            packetize_owner_raw_words(raw(E6,p))

    def test_zero_sized_a0_fails(self):
        with self.assertRaisesRegex(ValueError,"bounds"):
            packetize_owner_raw_words(raw(E6,[0xa0000000,0,0]))

    def test_huge_a0_image_outside_stage437_word_limit_fails(self):
        # 1024x512 is legal in VRAM, but exceeds the conservative JSONL
        # renderer's bounded 131075-word packet cap.
        with self.assertRaisesRegex(ValueError,"word limit"):
            packetize_owner_raw_words(raw(E6,[0xa0000000,0,0x02000400]))

    def test_invalid_source_types_and_size_limits_fail(self):
        for source in (b"",bytearray(raw(E6)),b"\0"*(MAX_RAW_BYTES+4)):
            with self.subTest(source_type=type(source)),self.assertRaises(ValueError):
                packetize_owner_raw_words(source)

    def test_private_packager_creates_exact_stage437_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            result=package_private_gp0_raw_capture(src,pre,out,frame=446)
            self.assertEqual(result["packet_count"],3)
            self.assertEqual(result["raw_word_count"],len(src.read_bytes())//4)
            hdr,packets,trace_hash=read_private_gp0_timeline(
                out,hashlib.sha256(pre.read_bytes()).hexdigest())
            self.assertEqual(hdr["frame"],446)
            self.assertEqual(packets,[E6,a0(COLORS),polygon()])
            self.assertEqual(trace_hash,hashlib.sha256(out.read_bytes()).hexdigest())
            self.assertTrue(result["full_frame_completeness_not_verified_by_packetization"])
            if os.name != "nt":
                self.assertEqual(out.stat().st_mode & 0o777,0o600)

    def test_packager_never_overwrites_existing_private_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            out.write_bytes(b"KEEP-ME")
            with self.assertRaises(FileExistsError):
                package_private_gp0_raw_capture(src,pre,out,frame=9)
            self.assertEqual(out.read_bytes(),b"KEEP-ME")

    def test_input_hash_mismatch_refuses_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            with self.assertRaisesRegex(ValueError,"disagrees"):
                package_private_gp0_raw_capture(src,pre,out,
                    frame=9,expected_raw_sha256="0"*64)
            self.assertFalse(out.exists())

    def test_input_hash_correct_does_not_pretend_to_attest_emulator(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            report=package_private_gp0_raw_capture(src,pre,out,frame=9,
                expected_raw_sha256=hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertTrue(report["raw_capture_is_original_emulator_trace_unverified"])
            self.assertTrue(report["matching_hashes_are_consistency_not_emulator_attestation"])

    def test_invalid_sha256_format_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            with self.assertRaisesRegex(ValueError,"lowercase"):
                package_private_gp0_raw_capture(
                    src,pre,out,frame=9,expected_raw_sha256="not-sha")
            self.assertFalse(out.exists())

    def test_initial_vram_must_be_exact_1mib(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            pre.write_bytes(bytes(VRAM_BYTES-1))
            with self.assertRaisesRegex(ValueError,"geometry"):
                package_private_gp0_raw_capture(src,pre,out,frame=9)

    def test_bool_frame_is_not_accepted_as_integer(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            with self.assertRaisesRegex(ValueError,"nonnegative integer"):
                package_private_gp0_raw_capture(src,pre,out,frame=True)

    def test_symlink_input_refused_even_if_under_private_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            link=Path(tmp)/"gp0-link.u32le"
            link.symlink_to(src)
            with self.assertRaisesRegex(ValueError,"symlinks"):
                package_private_gp0_raw_capture(link,pre,out,frame=1)
            self.assertFalse(out.exists())

    def test_no_raw_image_pixels_or_packet_words_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,pre,out=fixture(tmp)
            result=package_private_gp0_raw_capture(src,pre,out,frame=1)
            dump=json.dumps(result)
            for forbidden in ('"raw_a0_pixels"','"palette_u16"',
                              '"gp0_words"','"original_disc_file"'):
                self.assertNotIn(forbidden,dump)
            self.assertTrue(result["all_trace_and_hash_metadata_owner_private"])


if __name__=="__main__":
    unittest.main()
