"""Stage516 ROM-free private archive sealing and re-download verification."""
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from seal_private_player_frame1_archive import seal,verify
from test_verify_private_gpudump_player_step1_roi_offset import (
    synthetic_pair, X, Y, W, H, image, PIXELS,
)

ROI={"x":X,"y":Y,"width":W,"height":H}
MANIFEST="stage516-frame1.private.json"


def evidence(root):
    paths=synthetic_pair(root)
    names=dict(zip(("native","pretrace","gp0","v2","png"),
                   (p.name for p in paths)))
    return paths,names


class Stage516ArchiveTests(unittest.TestCase):
    def test_seal_then_verify_five_original_bytes_with_rgb_binding(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            result=seal(td,names,roi=ROI,require_changed_roi=True)
            self.assertTrue(verify(td))
            self.assertEqual(result["schema"],1)
            self.assertEqual(len(result["files"]),5)
            self.assertIn("UNATTESTED_SCREENSHOT_ORIGIN",result["result"])
            self.assertNotIn(str(td),Path(td,MANIFEST).read_text())
            if os.name=="posix":
                self.assertEqual(stat.S_IMODE(Path(td,MANIFEST).stat().st_mode),0o600)

    def test_private_manifest_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            seal(td,names,roi=ROI)
            with self.assertRaises(FileExistsError):
                seal(td,names,roi=ROI)

    def test_changed_png_bytes_detected_after_sealing(self):
        with tempfile.TemporaryDirectory() as td:
            paths,names=evidence(td)
            seal(td,names,roi=ROI)
            paths[-1].write_bytes(paths[-1].read_bytes()+b"changed")
            with self.assertRaisesRegex(ValueError,"differs from manifest"):
                verify(td)

    def test_changed_v2_snapshot_detected_after_sealing(self):
        with tempfile.TemporaryDirectory() as td:
            paths,names=evidence(td)
            seal(td,names,roi=ROI)
            payload=bytearray(paths[3].read_bytes())
            payload[-1]^=1
            paths[3].write_bytes(payload)
            with self.assertRaisesRegex(ValueError,"differs from manifest"):
                verify(td)

    def test_downloaded_clone_in_new_directory_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"source"
            destination=Path(td)/"download"
            source.mkdir()
            destination.mkdir()
            _,names=evidence(source)
            seal(source,names,roi=ROI)
            for p in source.iterdir():
                shutil.copyfile(p,destination/p.name)
            self.assertTrue(verify(destination))

    def test_bad_rgba_roi_does_not_create_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            paths,names=evidence(td)
            paths[-1].write_bytes(image((PIXELS[W:],PIXELS[:W])))
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                seal(td,names,roi=ROI)
            self.assertFalse(Path(td,MANIFEST).exists())

    def test_malformed_names_and_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            for bad in ("../private.bin","/root.bin","a/b.bin",".."):
                with self.subTest(bad=bad),self.assertRaises(ValueError):
                    seal(td,{**names,"native":bad},roi=ROI)
            self.assertFalse(Path(td,MANIFEST).exists())

    def test_aliased_file_roles_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            with self.assertRaisesRegex(ValueError,"distinct filenames"):
                seal(td,{**names,"gp0":names["native"]},roi=ROI)

    def test_symlink_and_hardlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths,names=evidence(td)
            target=Path(td)/"duplicate.gpudump"
            try:
                os.link(paths[0],target)
            except OSError:
                self.skipTest("hardlink unsupported")
            with self.assertRaisesRegex(ValueError,"unlinked"):
                seal(td,names,roi=ROI)
            target.unlink()
            original=paths[0]
            original.rename(target)
            original.symlink_to(target)
            with self.assertRaisesRegex(ValueError,"regular"):
                seal(td,names,roi=ROI)

    def test_unknown_manifest_claim_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            seal(td,names,roi=ROI)
            manifest=Path(td,MANIFEST)
            record=json.loads(manifest.read_text())
            record["origin"]="attested_by_emulator"
            manifest.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"schema or provenance"):
                verify(td)

    def test_forged_manifest_file_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            seal(td,names,roi=ROI)
            manifest=Path(td,MANIFEST)
            record=json.loads(manifest.read_text())
            record["files"]["png"]["sha256"]="0"*64
            manifest.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"differs from manifest"):
                verify(td)

    def test_missing_gp1_window_fails_before_archive_publication(self):
        with tempfile.TemporaryDirectory() as td:
            _,names=evidence(td)
            with self.assertRaisesRegex(ValueError,"not proven"):
                seal(td,names,roi=ROI,require_gp1=True)
            self.assertFalse(Path(td,MANIFEST).exists())


if __name__=="__main__":
    unittest.main()
