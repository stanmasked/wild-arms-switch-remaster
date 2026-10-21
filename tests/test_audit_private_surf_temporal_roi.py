"""Synthetic-only Surf Village two-reference temporal consistency regressions."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_private_surf_temporal_roi import (  # noqa: E402
    temporal_consistency_mask, assess_rendered_candidate,
    compare_private_reference_frames,
)

try:
    from PIL import Image
    from io import BytesIO
    from capture_private_pcsx_frame_witness import capture_private_frame_witness
    from test_capture_private_pcsx_frame_witness import expected_sequence
    PIL_AVAILABLE=True
except ImportError:
    PIL_AVAILABLE=False


def rgb(*pixels):
    return bytes(value for pixel in pixels for value in pixel)


class Stage434CoreTests(unittest.TestCase):
    def test_identical_frames_all_temporally_consistent(self):
        a=rgb((10,20,30),(40,50,60))
        mask,report=temporal_consistency_mask(a,a,2,1)
        self.assertEqual(mask,b"\x01\x01")
        self.assertEqual(report["temporally_changed_pixel_count"],0)
        self.assertEqual(report["temporally_consistent_fraction"],1)

    def test_changed_one_channel_at_one_pixel(self):
        a=rgb((10,20,30),(40,50,60))
        b=rgb((11,20,30),(40,50,60))
        mask,report=temporal_consistency_mask(a,b,2,1)
        self.assertEqual(mask,b"\x00\x01")
        self.assertEqual(report["temporally_changed_pixel_count"],1)
        self.assertEqual(report["temporally_consistent_fraction"],0.5)
        self.assertEqual(len(report["temporal_mask_sha256"]),64)

    def test_temporal_tolerance_is_max_rgb_channel_difference(self):
        a=rgb((0,10,20),(30,40,50))
        b=rgb((2,11,20),(33,40,50))
        mask,_=temporal_consistency_mask(a,b,2,1,tolerance=2)
        self.assertEqual(mask,b"\x01\x00")

    def test_changed_pixel_does_not_hide_all_pixel_mismatch(self):
        a=rgb((0,0,0),(80,80,80))
        b=rgb((50,0,0),(80,80,80))
        mask,_=temporal_consistency_mask(a,b,2,1)
        candidate=rgb((55,0,0),(80,80,80))
        result=assess_rendered_candidate(a,candidate,mask,2,1)
        self.assertEqual(result["all_pixel_comparison"][
            "threshold_exceeding_pixel_count"],1)
        self.assertEqual(result["stable_only_comparison"][
            "threshold_exceeding_stable_pixel_count"],0)
        self.assertEqual(result[
            "temporally_changed_pixels_excluded_from_stable_only_score"],1)
        self.assertTrue(result["all_pixel_metrics_are_not_masked"])

    def test_stable_pixel_error_calculates_exact_metrics(self):
        reference=rgb((0,0,0),(10,10,10))
        later=rgb((20,20,20),(10,10,10))
        mask,_=temporal_consistency_mask(reference,later,2,1)
        candidate=rgb((10,0,0),(13,10,10))
        result=assess_rendered_candidate(reference,candidate,mask,2,1)
        stable=result["stable_only_comparison"]
        self.assertEqual(stable["stable_pixel_count"],1)
        self.assertEqual(stable["threshold_exceeding_stable_pixel_count"],1)
        self.assertEqual(stable["stable_max_absolute_rgb_channel_error"],3)
        self.assertEqual(stable["stable_rgb_mean_absolute_channel_error"],1)
        self.assertEqual(result["all_pixel_comparison"]["threshold_exceeding_pixel_count"],2)

    def test_zero_stable_pixels_returns_no_stable_score(self):
        a=rgb((0,0,0),(0,0,0))
        b=rgb((1,0,0),(0,1,0))
        mask,_=temporal_consistency_mask(a,b,2,1)
        result=assess_rendered_candidate(a,a,mask,2,1)
        self.assertIsNone(result["stable_only_comparison"])
        self.assertEqual(result["temporally_changed_pixels_excluded_from_stable_only_score"],2)

    def test_candidate_error_threshold_affects_only_mismatch_classification(self):
        a=rgb((2,2,2))
        c=rgb((4,2,2))
        mask=b"\x01"
        result=assess_rendered_candidate(a,c,mask,1,1,error_threshold=2)
        self.assertEqual(result["stable_only_comparison"][
            "threshold_exceeding_stable_pixel_count"],0)
        self.assertEqual(result["all_pixel_comparison"]["exact_matching_pixel_count"],0)

    def test_reject_wrong_rgb_length(self):
        for left,right in ((b"",bytes(3)),(bytes(3),bytes(2)),
                           (bytearray(3),bytes(3))):
            with self.subTest(length=len(left)),self.assertRaises(ValueError):
                temporal_consistency_mask(left,right,1,1)

    def test_reject_invalid_mask_and_dimensions(self):
        for mask in (b"", b"\x02", "1", bytearray([1])):
            with self.subTest(mask=str(mask)),self.assertRaises(ValueError):
                assess_rendered_candidate(bytes(3),bytes(3),mask,1,1)
        with self.assertRaises(ValueError):
            temporal_consistency_mask(bytes(3),bytes(3),True,1)
        with self.assertRaises(ValueError):
            temporal_consistency_mask(bytes(3),bytes(3),1,1,tolerance=-1)
        with self.assertRaises(ValueError):
            temporal_consistency_mask(bytes(3),bytes(3),1,1,tolerance=256)

    def test_temporal_hash_is_deterministic(self):
        a=rgb((1,2,3),(4,5,6))
        b=rgb((1,2,3),(6,5,4))
        mask,info=temporal_consistency_mask(a,b,2,1)
        self.assertEqual(info["temporal_mask_sha256"],
                         hashlib.sha256(mask).hexdigest())

    def test_privacy_metrics_carry_no_original_raw_pixels(self):
        a=rgb((11,22,33))
        mask,stats=temporal_consistency_mask(a,a,1,1)
        scores=assess_rendered_candidate(a,a,mask,1,1)
        serialized=json.dumps({"mask":stats,"scores":scores})
        for field in ('"raw_pixels"','"palette_u16"','"decoded_original_rgb"'):
            self.assertNotIn(field,serialized)
        self.assertTrue(stats["temporal_mask_is_not_a_semantic_static_tile_label"])


@unittest.skipUnless(PIL_AVAILABLE,"Pillow needed only for private screenshot integration")
class Stage434PrivateIntegrationTests(unittest.TestCase):
    def make_capture(self,folder,basename,*,screen=None,disc=None):
        capture_private_frame_witness(folder,basename=basename,
                                      opener=expected_sequence(png=screen,disc=disc))

    def make_png(self,*colors):
        buffer=BytesIO()
        picture=Image.new("RGB",(len(colors),1))
        for x,color in enumerate(colors):
            picture.putpixel((x,0),color)
        picture.save(buffer,format="PNG")
        return buffer.getvalue()

    def test_one_changed_original_pixel_masked_only_in_stable_score(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            output=folder/"out";output.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second",screen=self.make_png(
                (255,0,0),(0,0,255)))
            candidate=folder/"candidate.png"
            candidate.write_bytes(self.make_png((255,0,0),(0,255,0)))
            report=compare_private_reference_frames(folder,"first","second",
                       output,"roof_probe",x=0,y=0,width=2,height=1,
                       candidate_png=candidate)
            self.assertEqual(report["mask_stats"]["temporally_consistent_pixel_count"],1)
            self.assertEqual(report["mask_stats"]["temporally_changed_pixel_count"],1)
            self.assertEqual(report["candidate_comparison"]["all_pixel_comparison"][
                "threshold_exceeding_pixel_count"],1)
            self.assertEqual(report["candidate_comparison"]["stable_only_comparison"][
                "threshold_exceeding_stable_pixel_count"],0)
            self.assertEqual(len(list(output.iterdir())),5)
            with Image.open(output/"roof_probe.temporal-mask.png") as picture:
                self.assertEqual(picture.convert("RGB").getpixel((0,0)),(255,255,255))
                self.assertEqual(picture.convert("RGB").getpixel((1,0)),(0,0,0))

    def test_identical_captures_are_flagged_not_certified(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            result=compare_private_reference_frames(folder,"first","second",
                    out,"same",x=0,y=0,width=2,height=1)
            self.assertTrue(result["screenshots_byte_identical"])
            self.assertTrue(result["interpretation"][
                "stable_pixels_mean_consistent_only_in_two_observations"])
            self.assertIsNone(result["candidate_comparison"])

    def test_wrong_screenshot_geometry_rejected_without_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second",screen=self.make_png(
                (255,0,0),(255,0,0),(255,0,0)))
            with self.assertRaisesRegex(ValueError,"screen dimensions differ"):
                compare_private_reference_frames(folder,"first","second",
                    out,"fail",x=0,y=0,width=2,height=1)
            self.assertEqual(list(out.iterdir()),[])

    def test_cd_info_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second",disc=b'{"disc":"synthetic-different"}')
            with self.assertRaisesRegex(ValueError,"CD-info byte fingerprints differ"):
                compare_private_reference_frames(folder,"first","second",
                    out,"fail",x=0,y=0,width=2,height=1)
            self.assertEqual(list(out.iterdir()),[])

    def test_original_screenshot_tampering_fails_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            (folder/"second.screen.png").write_bytes(self.make_png(
                (0,0,0),(0,0,0)))
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                compare_private_reference_frames(folder,"first","second",
                    out,"fail",x=0,y=0,width=2,height=1)
            self.assertEqual(list(out.iterdir()),[])

    def test_candidate_bad_geometry_rejected_no_resample(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            candidate=folder/"c.png"
            candidate.write_bytes(self.make_png((255,0,0)))
            with self.assertRaisesRegex(ValueError,"no scaling permitted"):
                compare_private_reference_frames(folder,"first","second",
                    out,"fail",x=0,y=0,width=2,height=1,candidate_png=candidate)
            self.assertEqual(list(out.iterdir()),[])

    def test_no_clobber_existing_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            target=out/"test.temporal-mask.png"
            target.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                compare_private_reference_frames(folder,"first","second",
                    out,"test",x=0,y=0,width=2,height=1)
            self.assertEqual(target.read_bytes(),b"KEEP")

    def test_same_basename_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            with self.assertRaisesRegex(ValueError,"independently named"):
                compare_private_reference_frames(folder,"same","same",
                    out,"fail",x=0,y=0,width=2,height=1)

    def test_out_of_bounds_roi_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            with self.assertRaisesRegex(ValueError,"outside original"):
                compare_private_reference_frames(folder,"first","second",
                    out,"fail",x=1,y=0,width=2,height=1)

    def test_produces_only_metadata_in_json_not_png_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);out=folder/"out";out.mkdir()
            self.make_capture(folder,"first")
            self.make_capture(folder,"second")
            report=compare_private_reference_frames(folder,"first","second",
                    out,"private",x=0,y=0,width=2,height=1)
            stored=json.loads((out/"private.evidence.json").read_text())
            self.assertEqual(stored["kind"],"WA1_PRIVATE_SURF_TEMPORAL_ROI_CONSISTENCY")
            self.assertEqual(stored["mask_stats"]["roi_pixel_count"],2)
            self.assertTrue(stored["interpretation"]["all_outputs_stay_private"])
            self.assertEqual(report["first_roi_rgb_sha256"],stored["first_roi_rgb_sha256"])


if __name__=="__main__":
    unittest.main()
