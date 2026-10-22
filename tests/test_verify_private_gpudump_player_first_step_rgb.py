"""Stage454: synthetic-only Player first-Step postframe VRAM/PNG checks."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_private_gpudump_player_first_step_rgb import verify_private_gpudump_player_first_step
from test_verify_private_pcsx_native_gpudump_import import prepared
from test_verify_private_gpudump_player_rewind_rgb import png
from test_import_private_pcsx_native_gpudump import base_records
from import_private_pcsx_native_gpudump import GP0, GP1, VSYNC


def fixture(root,*,word=None,image=None,records=None):
    native,pre,trace=prepared(Path(root),records=records)
    after=Path(root)/"poststep.u16le.bin"
    data=bytearray(pre.read_bytes())
    if word is not None:
        for index in (0,1):
            data[index*2:index*2+2]=word.to_bytes(2,"little")
    after.write_bytes(data)
    pic=Path(root)/"poststep.png"
    if image is None:
        image=png((248,0,0) if word is not None and word&0x7fff==31
                  else (0,0,0))
    pic.write_bytes(image)
    return native,pre,trace,after,pic


def check(paths,**opts):
    return verify_private_gpudump_player_first_step(
        *paths,x=0,y=0,width=2,height=1,**opts)


class Stage454FirstStepTests(unittest.TestCase):
    def test_changed_poststep_pixels_match_but_source_is_unattested(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,word=31)
            out=check(paths,expected_frame=449,
                      expected_player_frame_label=1)
            self.assertEqual(out["status"],
                "POST_STEP_ONE_RGB_EQUALITY_UNATTESTED_PLAYER_SNAPSHOT")
            self.assertEqual(out["change_since_initial_rewind"][
                "whole_vram_changed_u16_halfword_count"],2)
            self.assertEqual(out["change_since_initial_rewind"][
                "roi_visibly_changed_rgb555_pixel_count"],2)
            self.assertTrue(out["interpretation"][
                "poststep_vram_origin_from_player_is_not_authenticated"])

    def test_identical_poststep_state_not_claimed_to_prove_replay(self):
        with tempfile.TemporaryDirectory() as d:
            result=check(fixture(d))
            self.assertTrue(result["roi_rgb_exactly_equal"])
            self.assertTrue(result["change_since_initial_rewind"][
                "poststep_vram_identical_to_initial_pretrace"])

    def test_optional_changed_roi_gate(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d)
            with self.assertRaisesRegex(ValueError,"no visible RGB555 change"):
                check(paths,require_changed_roi=True)
            paths[3].write_bytes(bytes([31,0,31,0])+
                                 paths[3].read_bytes()[4:])
            paths[4].write_bytes(png((248,0,0)))
            self.assertTrue(check(paths,require_changed_roi=True)["roi_rgb_exactly_equal"])

    def test_bit15_only_change_is_not_visible(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,word=0x8000)
            result=check(paths)
            delta=result["change_since_initial_rewind"]
            self.assertEqual(delta["whole_vram_changed_u16_halfword_count"],2)
            self.assertEqual(delta["roi_visibly_changed_rgb555_pixel_count"],0)

    def test_wrong_poststep_png_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,word=31,image=png())
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                check(paths)

    def test_wrong_png_diagnostic_optin_does_not_claim_binding(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,word=31,image=png())
            result=check(paths,require_exact_rgb=False)
            self.assertEqual(result["status"],
                "POST_STEP_ONE_RGB_MISMATCH_NO_VISUAL_BINDING")
            self.assertEqual(result["roi_mismatched_rgb_pixel_count"],2)

    def test_operator_frame_label_only_one_or_absent(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d)
            for value in (0,2,-1,True,"1"):
                with self.subTest(value=value),self.assertRaisesRegex(
                        ValueError,"frame label 1"):
                    check(paths,expected_player_frame_label=value)

    def test_independent_poststep_digest_checks(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,word=31)
            digest=hashlib.sha256(paths[3].read_bytes()).hexdigest()
            pngsha=hashlib.sha256(paths[4].read_bytes()).hexdigest()
            result=check(paths,expected_poststep_vram_sha256=digest,
                         expected_poststep_png_sha256=pngsha)
            self.assertTrue(result["independent_poststep_vram_digest_compared"])
            self.assertTrue(result["independent_poststep_png_digest_compared"])
            with self.assertRaisesRegex(ValueError,"independent expected SHA-256"):
                check(paths,expected_poststep_vram_sha256="0"*64)

    def test_tampered_native_trace_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d)
            trace=paths[2]
            lines=trace.read_text().splitlines()
            event=json.loads(lines[-1]);event["words"][-1]^=1
            lines[-1]=json.dumps(event)
            trace.write_text("\n".join(lines)+"\n")
            with self.assertRaisesRegex(ValueError,"packet differs"):
                check(paths)

    def test_partial_poststep_vram_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d)
            paths[3].write_bytes(paths[3].read_bytes()[:-2])
            with self.assertRaisesRegex(ValueError,"invalid or aliased"):
                check(paths)

    def test_png_must_be_correct_unscaled_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,image=png(width=3))
            with self.assertRaisesRegex(ValueError,"unscaled exact ROI"):
                check(paths)

    def test_native_gp1_display_window_can_be_required(self):
        with tempfile.TemporaryDirectory() as d:
            records=base_records()
            records[5]=(GP1,[0x05000000,0x08000000])
            paths=fixture(d,records=records)
            with self.assertRaisesRegex(ValueError,"differs from native GP1"):
                check(paths,require_native_display_window=True)

    def test_multi_frame_native_dump_only_uses_first_step(self):
        with tempfile.TemporaryDirectory() as d:
            paths=fixture(d,records=base_records()+[
                (GP0,[0]),(VSYNC,[5678,0])])
            out=check(paths)
            self.assertEqual(out["native_first_step_vsync_gpu_cycle"],1234)

    def test_report_excludes_source_words_and_png_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            out=check(fixture(d,word=31))
            dumped=json.dumps(out)
            for key in ('"raw_png_pixels"','"original_gp0_words"',
                        '"original_palette_bytes"','"disc_serial"'):
                self.assertNotIn(key,dumped)
            self.assertTrue(out["interpretation"][
                "all_hashes_and_reports_must_remain_owner_private"])


if __name__=="__main__":
    unittest.main()
