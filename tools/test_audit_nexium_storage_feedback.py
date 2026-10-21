#!/usr/bin/env python3
"""Synthetic NeXium desktops prove strict projected plaque audit."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, screen_point
from audit_nexium_storage_feedback import (
    CAPTURES, SAVE_COLORS, LOAD_COLORS, GAME_ROI, DARK,
    audit_feedback_images, projected_notice,
)


def synthetic(directory):
    folder = Path(directory)
    folder.mkdir(exist_ok=True)
    for name, possible in CAPTURES:
        desktop = Image.new("RGB", SCREEN_SIZE, (20, 35, 50))
        overlay = projected_notice(next(iter(possible)))
        desktop.paste(overlay, (VIEW_X, 0))
        desktop.save(folder / (name + ".png"))
    return folder


class StorageFeedbackAuditTests(unittest.TestCase):
    def test_four_valid_guest_indicators_exact_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            report=audit_feedback_images(folder,Path(tmp)/"report.json")
            self.assertTrue(report["all_four_indicators_valid"])
            self.assertEqual(report["total_mismatched_pixels"],0)
            self.assertEqual(len(report["records"]),4)
            self.assertGreater(report["total_compared_pixels"],20000)

    def test_reject_missing_file_and_wrong_color(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            (folder/"save-event.png").unlink()
            with self.assertRaises(ValueError):
                audit_feedback_images(folder,Path(tmp)/"report.json")
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            wrong=folder/"load-start.png"
            desktop=Image.new("RGB",SCREEN_SIZE,(20,35,50))
            desktop.paste(projected_notice(next(iter(SAVE_COLORS))), (VIEW_X,0))
            desktop.save(wrong)
            report=audit_feedback_images(folder,Path(tmp)/"report.json")
            self.assertFalse(report["all_four_indicators_valid"])
            self.assertFalse(report["records"][1]["color_match"])

    def test_same_color_with_wrong_letters_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            same_color=next(iter(SAVE_COLORS))
            desktop=Image.new("RGB",SCREEN_SIZE,(20,35,50))
            desktop.paste(projected_notice(same_color,label="RAM ONLY"),(VIEW_X,0))
            desktop.save(folder/"save-start.png")
            report=audit_feedback_images(folder,Path(tmp)/"report.json")
            self.assertFalse(report["all_four_indicators_valid"])
            self.assertTrue(report["records"][0]["color_match"])
            self.assertGreater(
                report["records"][0]["mismatched_projected_plaque_pixels"],10)

    def test_single_changed_pixel_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            target=folder/"save-event.png"
            with Image.open(target) as image:
                desktop=image.convert("RGB")
            x=(GAME_ROI[0]+GAME_ROI[2])//2
            y=(GAME_ROI[1]+GAME_ROI[3])//2
            original=desktop.getpixel((x,y))
            replacement=(0,0,0) if original!=(0,0,0) else (255,0,0)
            desktop.putpixel((x,y),replacement)
            desktop.save(target)
            report=audit_feedback_images(folder,Path(tmp)/"report.json")
            self.assertFalse(report["all_four_indicators_valid"])
            self.assertEqual(
                report["records"][2]["mismatched_projected_plaque_pixels"],1)

    def test_invalid_desktop_dimensions_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=synthetic(Path(tmp)/"feedback")
            Image.new("RGB",(600,450),(40,55,66)).save(folder/"load-event.png")
            with self.assertRaises(ValueError):
                audit_feedback_images(folder,Path(tmp)/"report.json")


if __name__ == "__main__":
    unittest.main()
