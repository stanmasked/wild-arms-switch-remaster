"""ROM-free and optional synthetic PNG tests for Stage433 PS1 frame ROI evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_private_surf_reference_patch import (  # noqa: E402
    compare_opaque_rgb, create_private_surf_reference_patch, validate_roi,
)
from capture_private_pcsx_frame_witness import capture_private_frame_witness  # noqa: E402

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def rgb(*pixels):
    return bytes(channel for pixel in pixels for channel in pixel)


class Stage433PatchEvidenceTests(unittest.TestCase):
    def test_exact_reference_roi_edges(self):
        self.assertEqual(validate_roi(0, 0, 32, 12, 32, 12), (0, 0, 32, 12))
        self.assertEqual(validate_roi(3, 4, 2, 5, 20, 20), (3, 4, 5, 9))

    def test_reject_roi_outside_frame_and_invalid_area(self):
        bad = [
            (-1,0,1,1,10,10), (0,-1,1,1,10,10),
            (0,0,0,1,10,10), (0,0,1,0,10,10),
            (9,0,2,1,10,10), (0,9,1,2,10,10),
            (0,0,1025,1025,4096,4096),
            (0,0,1,1,0,10),
        ]
        for values in bad:
            with self.subTest(values=values),self.assertRaises(ValueError):
                validate_roi(*values)

    def test_reject_boolean_and_fractional_roi(self):
        for bad in (True,1.25,"1"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_roi(bad,0,1,1,10,10)

    def test_perfect_image_match_has_zero_metrics_and_zero_difference(self):
        frame=rgb((1,2,3),(4,5,6),(7,8,9),(10,11,12))
        report,difference=compare_opaque_rgb(frame,frame,2,2)
        self.assertEqual(report["exact_matching_pixel_count"],4)
        self.assertEqual(report["threshold_exceeding_pixel_count"],0)
        self.assertIsNone(report["threshold_exceeding_bounds_xyxy_inclusive"])
        self.assertEqual(report["mean_absolute_rgb_channel_error"],0)
        self.assertEqual(report["root_mean_square_rgb_channel_error"],0)
        self.assertEqual(difference,bytes(12))

    def test_exact_per_channel_error_and_bounds(self):
        a=rgb((0,0,0),(3,4,5),(10,20,30),(60,60,60))
        b=rgb((0,0,0),(3,4,6),(13,20,30),(60,60,60))
        report,diff=compare_opaque_rgb(a,b,2,2)
        self.assertEqual(report["pixel_count"],4)
        self.assertEqual(report["exact_matching_pixel_count"],2)
        self.assertEqual(report["threshold_exceeding_pixel_count"],2)
        self.assertEqual(report["threshold_exceeding_pixel_fraction"],0.5)
        self.assertEqual(report["mean_absolute_rgb_channel_error"],round(4/12,8))
        self.assertEqual(report["max_absolute_rgb_channel_error"],3)
        self.assertEqual(report["threshold_exceeding_bounds_xyxy_inclusive"],[0,0,1,1])
        self.assertEqual(diff,rgb((0,0,0),(0,0,1),(3,0,0),(0,0,0)))

    def test_threshold_applies_to_max_channel_difference(self):
        a=rgb((10,10,10),(20,20,20))
        b=rgb((12,11,10),(24,20,20))
        report,_=compare_opaque_rgb(a,b,2,1,threshold=2)
        self.assertEqual(report["threshold_exceeding_pixel_count"],1)
        self.assertEqual(report["exact_matching_pixel_count"],0)
        self.assertEqual(report["threshold_exceeding_bounds_xyxy_inclusive"],[1,0,1,0])
        self.assertEqual(report["absolute_error_threshold_per_channel"],2)

    def test_large_error_and_rmse(self):
        report,diff=compare_opaque_rgb(rgb((0,0,0)),rgb((255,0,0)),1,1)
        self.assertEqual(report["max_absolute_rgb_channel_error"],255)
        self.assertEqual(report["mean_absolute_rgb_channel_error"],85)
        self.assertEqual(report["root_mean_square_rgb_channel_error"],
                         round((255*255/3)**0.5,8))
        self.assertEqual(diff,b"\xff\x00\x00")

    def test_reject_mismatched_buffer_size(self):
        for ref,candidate in (
                (b"",bytes(3)), (bytes(3),bytes(2)),
                (bytes(6),bytes(3)), (bytearray(3),bytes(3))):
            with self.subTest(ref_len=len(ref)),self.assertRaises(ValueError):
                compare_opaque_rgb(ref,candidate,1,1)

    def test_reject_invalid_dimensions_and_threshold(self):
        values=[(0,1,0), (1,-1,0),(True,1,0),
                (1,True,0),(1,1,-1),(1,1,256),
                (1,1,True),(1,1,1.0),(2000,2000,0)]
        for width,height,threshold in values:
            with self.subTest(values=(width,height,threshold)),self.assertRaises(ValueError):
                compare_opaque_rgb(bytes(3),bytes(3),width,height,threshold=threshold)

    def test_diff_bounds_in_nonzero_y_and_x(self):
        a=bytes(4*3*3)
        b=bytearray(a)
        b[(2*4+3)*3+2]=1
        report,_=compare_opaque_rgb(a,bytes(b),4,3)
        self.assertEqual(report["threshold_exceeding_bounds_xyxy_inclusive"],[3,2,3,2])

    def test_empty_private_output_directory_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"directory must already exist"):
                create_private_surf_reference_patch(
                    td,"capture",Path(td)/"no-such-dir","roi",
                    x=0,y=0,width=1,height=1)

    def test_invalid_output_basename_denied(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                create_private_surf_reference_patch(
                    td,"capture",td,"../escape",x=0,y=0,width=1,height=1)

    def test_provenance_verified_before_image_decode(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("audit_private_surf_reference_patch.verify_private_frame_witness",
                       side_effect=ValueError("untrusted Stage432 capture")) as gate:
                with patch("audit_private_surf_reference_patch._opaque_rgb_png") as decoder:
                    with self.assertRaisesRegex(ValueError,"untrusted Stage432"):
                        create_private_surf_reference_patch(
                            td,"bad_witness",td,"patch",
                            x=0,y=0,width=1,height=1)
                    gate.assert_called_once()
                    decoder.assert_not_called()

    def test_no_secret_raw_pixels_in_comparison_metadata(self):
        a=rgb((11,22,33))
        report,diff=compare_opaque_rgb(a,a,1,1)
        serialized=json.dumps(report)
        for forbidden in ('"original_rgb_bytes"','"source_palette_words"',
                          '"decoded_original_tiles"'):
            self.assertNotIn(forbidden,serialized)
        self.assertEqual(diff,bytes(3))


@unittest.skipUnless(PIL_AVAILABLE, "Pillow required only for private PNG export")
class Stage433PrivatePngTests(unittest.TestCase):
    def make_witness(self, directory, name="frame"):
        sys.path.insert(0,str(Path(__file__).parent))
        from test_capture_private_pcsx_frame_witness import expected_sequence
        capture_private_frame_witness(directory,basename=name,
                                      opener=expected_sequence())

    def test_reference_only_crop_and_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            output=folder/"out"
            output.mkdir()
            self.make_witness(folder)
            report=create_private_surf_reference_patch(
                folder,"frame",output,"reference",x=0,y=0,width=2,height=1)
            self.assertFalse(report["candidate_supplied"])
            self.assertIsNone(report["comparison"])
            self.assertTrue(report["interpretation"][
                "not_an_automatic_reference_certification"])
            self.assertEqual(sorted(p.name for p in output.iterdir()),[
                "reference.evidence.json","reference.reference.png"])
            with Image.open(output/"reference.reference.png") as img:
                self.assertEqual(img.size,(2,1))
                self.assertEqual(img.convert("RGB").getpixel((0,0)),(255,0,0))

    def test_pixel_exact_candidate_and_triptych(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            candidate=folder/"candidate.png"
            Image.new("RGB",(2,1),(255,0,0)).save(candidate)
            report=create_private_surf_reference_patch(
                folder,"frame",output,"comparison",x=0,y=0,width=2,height=1,
                candidate_png=candidate)
            self.assertEqual(report["comparison"]["exact_matching_pixel_count"],2)
            self.assertEqual(report["comparison"]["threshold_exceeding_pixel_count"],0)
            self.assertTrue(report["comparison"][
                "image_metric_is_not_proof_of_original_palette_assignment"])
            with Image.open(output/"comparison.comparison.png") as result:
                self.assertEqual(result.size,(2*3+2*10,1))
            self.assertEqual(len(list(output.iterdir())),3)

    def test_candidate_one_pixel_error_reported(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            candidate=folder/"different.png"
            Image.new("RGB",(2,1),(0,0,255)).save(candidate)
            report=create_private_surf_reference_patch(
                folder,"frame",output,"different",x=0,y=0,width=2,height=1,
                candidate_png=candidate)
            self.assertEqual(report["comparison"]["threshold_exceeding_pixel_count"],2)
            self.assertEqual(report["comparison"]["max_absolute_rgb_channel_error"],255)

    def test_no_resampling_incorrect_candidate_size(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            candidate=folder/"wrong.png"
            Image.new("RGB",(1,1),(255,0,0)).save(candidate)
            with self.assertRaisesRegex(ValueError,"match ROI dimensions exactly"):
                create_private_surf_reference_patch(
                    folder,"frame",output,"wrong",x=0,y=0,width=2,height=1,
                    candidate_png=candidate)
            self.assertEqual(list(output.iterdir()),[])

    def test_alpha_candidate_rejected_without_implicit_compositing(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            candidate=folder/"alpha.png"
            Image.new("RGBA",(2,1),(255,0,0,120)).save(candidate)
            with self.assertRaisesRegex(ValueError,"transparent pixels"):
                create_private_surf_reference_patch(
                    folder,"frame",output,"alpha",x=0,y=0,width=2,height=1,
                    candidate_png=candidate)
            self.assertEqual(list(output.iterdir()),[])

    def test_reject_modified_original_screenshot_even_if_valid_png(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            Image.new("RGB",(2,1),(0,255,0)).save(folder/"frame.screen.png")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                create_private_surf_reference_patch(
                    folder,"frame",output,"tampered",x=0,y=0,width=2,height=1)
            self.assertEqual(list(output.iterdir()),[])

    def test_no_clobber_existing_patch_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root); output=folder/"out"; output.mkdir()
            self.make_witness(folder)
            target=output/"example.reference.png"
            target.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                create_private_surf_reference_patch(
                    folder,"frame",output,"example",x=0,y=0,width=2,height=1)
            self.assertEqual(target.read_bytes(),b"KEEP")
            self.assertEqual(list(output.iterdir()),[target])


if __name__ == "__main__":
    unittest.main()
