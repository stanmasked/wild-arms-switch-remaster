"""Stage453 synthetic-only PCSX GPU Dump Player rewind RGB witness checks."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_private_gpudump_player_rewind_rgb import (
    VRAM_BYTES,compare_private_rewind_vram_rgb,
    private_pretrace_display_rectangle,verify_private_gpudump_rewind_image,
)
from import_private_pcsx_native_gpudump import GP1,TRACE_BEGIN
from test_import_private_pcsx_native_gpudump import base_records
from test_verify_private_pcsx_native_gpudump_import import prepared


def png(color=(0,0,0),width=2,height=1, mode="RGB"):
    image=Image.new(mode,(width,height),color)
    stream=BytesIO()
    image.save(stream,format="PNG")
    return stream.getvalue()


def fixture(folder, *,image=None,records=None):
    folder=Path(folder)
    native,pre,trace=prepared(folder,records=records)
    picture=folder/"rewind-roi.png"
    picture.write_bytes(png() if image is None else image)
    return native,pre,trace,picture


def verify(paths,**options):
    return verify_private_gpudump_rewind_image(
        *paths,x=0,y=0,width=2,height=1,**options)


class Stage453PlayerRewindTests(unittest.TestCase):
    def test_exact_player_rewind_black_rgb_matches_native_pretrace(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td)
            result=verify(paths,expected_frame=449)
            self.assertEqual(result["status"],
                "REWIND_PRETRACE_RGB_EQUALITY_WITH_UNVERIFIED_PNG_PROVENANCE")
            self.assertTrue(result["compared_rewind_region"][
                "rgb_pixel_values_exactly_equal"])
            self.assertEqual(result["compared_rewind_region"][
                "compared_rgb_pixel_count"],2)
            self.assertTrue(result["interpretation"][
                "not_rendered_frame_after_first_native_vsync"])

    def test_independent_png_hash_is_checked(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td)
            digest=hashlib.sha256(paths[3].read_bytes()).hexdigest()
            r=verify(paths,expected_png_sha256=digest)
            self.assertEqual(r["owner_rewind_png_sha256"],digest)
            with self.assertRaisesRegex(ValueError,"expected hash"):
                verify(paths,expected_png_sha256="0"*64)

    def test_mismatched_rgb_fails_closed_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,image=png((248,0,0)))
            with self.assertRaisesRegex(ValueError,"RGB differs"):
                verify(paths)

    def test_mismatched_rgb_explicit_diagnostic_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,image=png((248,0,0)))
            report=verify(paths,require_exact_rgb=False)
            self.assertEqual(report["status"],
                             "REWIND_PNG_RGB_MISMATCH_NO_VISUAL_BINDING")
            self.assertFalse(report["compared_rewind_region"][
                "rgb_pixel_values_exactly_equal"])
            self.assertEqual(report["compared_rewind_region"][
                             "mismatched_rgb_pixel_count"],2)

    def test_rgb555_low_five_bits_are_shifted_not_gamma_or_rescaled(self):
        data=bytearray(VRAM_BYTES)
        data[0:2]=(0x001f).to_bytes(2,"little")
        data[2:4]=(0x03e0).to_bytes(2,"little")
        image=bytes((248,0,0, 0,248,0))
        result=compare_private_rewind_vram_rgb(data,image,0,0,2,1)
        self.assertTrue(result["rgb_pixel_values_exactly_equal"])
        self.assertEqual(result["maximum_absolute_rgb_channel_error"],0)

    def test_high_bit_15_does_not_affect_player_rgb_channels(self):
        data=bytearray(VRAM_BYTES)
        data[0:2]=(0x801f).to_bytes(2,"little")
        match=compare_private_rewind_vram_rgb(
            data,bytes((248,0,0)),0,0,1,1)
        self.assertTrue(match["rgb_pixel_values_exactly_equal"])
        self.assertTrue(match["bit15_mask_is_not_transparency_for_display"])

    def test_blue_channel_correctly_uses_u16_bits_10_to_14(self):
        data=bytearray(VRAM_BYTES)
        data[0:2]=(0x7c00).to_bytes(2,"little")
        result=compare_private_rewind_vram_rgb(
            data,bytes((0,0,248)),0,0,1,1)
        self.assertTrue(result["rgb_pixel_values_exactly_equal"])

    def test_region_offset_and_nonwrapping_row_coordinates(self):
        data=bytearray(VRAM_BYTES)
        offset=(12*1024+123)*2
        data[offset:offset+2]=(0x4210).to_bytes(2,"little")
        p=bytes((128,128,128))
        result=compare_private_rewind_vram_rgb(
            data,p,123,12,1,1)
        self.assertTrue(result["rgb_pixel_values_exactly_equal"])

    def test_rgb_mismatch_statistics_are_consistent(self):
        r=compare_private_rewind_vram_rgb(bytes(VRAM_BYTES),
                                         bytes((0,4,9,0,0,0)),0,0,2,1)
        self.assertEqual(r["mismatched_rgb_pixel_count"],1)
        self.assertEqual(r["matching_rgb_pixel_count"],1)
        self.assertEqual(r["maximum_absolute_rgb_channel_error"],9)
        self.assertEqual(r["mean_absolute_rgb_channel_error"],
                         round(13/6,8))

    def test_invalid_roi_or_image_byte_count_refused(self):
        source=bytes(VRAM_BYTES)
        for geometry in ((-1,0,1,1),(1023,0,2,1),
                         (0,511,1,2),(0,0,0,1),
                         (0,0,True,1),(0,0,2,1)):
            payload=bytes(3) if geometry[-2:]!=(2,1) else bytes(5)
            with self.subTest(geometry=geometry),self.assertRaises(ValueError):
                compare_private_rewind_vram_rgb(source,payload,*geometry)

    def test_transparent_png_cannot_verify_player_rgb(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,image=png((0,0,0,0),mode="RGBA"))
            with self.assertRaisesRegex(ValueError,"transparent"):
                verify(paths)

    def test_png_dimension_must_equal_exact_unscaled_roi(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,image=png(width=3))
            with self.assertRaisesRegex(ValueError,"exact unscaled"):
                verify(paths)

    def test_native_gp1_display_window_from_rewind_preamble(self):
        records=base_records()
        records[5]=(GP1,[0x03000000,0x05000000,0x08000000])
        with tempfile.TemporaryDirectory() as td:
            image=png(width=256,height=240)
            paths=fixture(td,records=records,image=image)
            report=verify_private_gpudump_rewind_image(
                *paths,x=0,y=0,width=256,height=240,
                require_native_display_window=True)
            self.assertTrue(report["native_gp1_display_window_explicitly_verified"])
            self.assertTrue(report["compared_rewind_region"][
                "rgb_pixel_values_exactly_equal"])

    def test_display_window_coordinates_reject_manual_subregion_override(self):
        records=base_records()
        records[5]=(GP1,[0x05000000,0x08000000])
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,records=records)
            with self.assertRaisesRegex(ValueError,"does not equal"):
                verify(paths,require_native_display_window=True)

    def test_unobserved_native_gp1_display_start_rejected(self):
        records=base_records()
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,records=records)
            with self.assertRaisesRegex(ValueError,"not proven"):
                verify(paths,require_native_display_window=True)

    def test_duplicate_native_gp1_restore_display_control_rejected(self):
        records=base_records()
        records[5]=(GP1,[0x05000000,0x05000000,0x08000000])
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,records=records)
            with self.assertRaisesRegex(ValueError,"duplicate"):
                verify(paths,require_native_display_window=True)

    def test_native_gp1_window_wraps_outside_vram_fail_closed(self):
        records=base_records()
        records[5]=(GP1,[0x050003ff,0x08000000])
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td,records=records)
            with self.assertRaisesRegex(ValueError,"wraps"):
                verify(paths,require_native_display_window=True)

    def test_native_gp1_width_and_height_bit_decode_matches_upstream(self):
        records=[(GP1,[0x05000000 | (10<<10) | 11,
                       0x08000000 | 0x40 | 0x24]),(TRACE_BEGIN,[])]
        self.assertEqual(private_pretrace_display_rectangle(records),
                         (11,10,368,480))

    def test_symlink_png_is_not_accepted_for_owner_private_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace,picture=fixture(td)
            link=Path(td)/"link.png"
            link.symlink_to(picture)
            with self.assertRaisesRegex(ValueError,"invalid or aliased"):
                verify((native,pre,trace,link))

    def test_native_dump_sha256_mismatch_detected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td)
            with self.assertRaisesRegex(ValueError,"independent SHA256"):
                verify(paths,expected_native_sha256="f"*64)

    def test_frame_label_is_operator_input_not_player_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td)
            r=verify(paths,expected_frame=449)
            self.assertTrue(r["interpretation"][
                "snapshot_is_at_player_rewind_before_first_live_gp0"])
            self.assertTrue(r["interpretation"][
                "png_actual_origin_from_player_ui_not_attested"])
            with self.assertRaisesRegex(ValueError,"frame differs"):
                verify(paths,expected_frame=0)

    def test_no_original_rgb_or_gpu_words_exported_in_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            paths=fixture(td)
            report=verify(paths)
            serialized=json.dumps(report)
            for forbidden in ('"original_rgb_bytes"',
                              '"original_gpu_packets"',
                              '"raw_clut_words"',
                              '"original_disc_data"'):
                self.assertNotIn(forbidden,serialized)
            self.assertTrue(report["interpretation"][
                "all_sha256_and_visual_metadata_must_remain_owner_private"])


if __name__=="__main__":
    unittest.main()
