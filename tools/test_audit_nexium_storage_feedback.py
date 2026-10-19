#!/usr/bin/env python3
"""Invented 1600x900 screenshots for the new real guest HUD audit."""
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
from audit_nexium_checkpoints import SCREEN_SIZE, screen_point
from audit_nexium_storage_feedback import (
    CAPTURES, SAVE_COLORS, LOAD_COLORS, WHITE, audit_feedback_images,
)


def synthetic(directory):
    folder = Path(directory)
    folder.mkdir(exist_ok=True)
    for name, possible in CAPTURES:
        image = Image.new("RGB", SCREEN_SIZE, (20, 35, 50))
        d = ImageDraw.Draw(image)
        accent = next(iter(possible))
        cx, cy = screen_point(1008, 54)
        d.rectangle((cx-8,cy-8,cx+8,cy+8), fill=accent)
        x,y=screen_point(1050,51)
        d.rectangle((x,y,x+9,y+9), fill=WHITE)
        image.save(folder / (name + ".png"))
    return folder


class StorageFeedbackAuditTests(unittest.TestCase):
    def test_four_valid_guest_indicators(self):
        with tempfile.TemporaryDirectory() as path:
            folder = synthetic(Path(path)/"feedback")
            report=audit_feedback_images(folder,Path(path)/"report.json")
            self.assertTrue(report["all_four_indicators_valid"])
            self.assertEqual(len(report["records"]),4)

    def test_reject_missing_file_and_wrong_color(self):
        with tempfile.TemporaryDirectory() as path:
            folder=synthetic(Path(path)/"feedback")
            (folder/"save-event.png").unlink()
            with self.assertRaises(ValueError):
                audit_feedback_images(folder,Path(path)/"report.json")
        with tempfile.TemporaryDirectory() as path:
            folder=synthetic(Path(path)/"feedback")
            bad=folder/"load-start.png"
            im=Image.open(bad).convert("RGB")
            cx,cy=screen_point(1008,54)
            ImageDraw.Draw(im).rectangle((cx-8,cy-8,cx+8,cy+8),
                                         fill=next(iter(SAVE_COLORS)))
            im.save(bad)
            result=audit_feedback_images(folder,Path(path)/"report.json")
            self.assertFalse(result["all_four_indicators_valid"])

    def test_color_square_without_text_fails(self):
        with tempfile.TemporaryDirectory() as path:
            folder=synthetic(Path(path)/"feedback")
            p=folder/"save-start.png"
            im=Image.open(p).convert("RGB")
            x,y=screen_point(1050,51)
            ImageDraw.Draw(im).rectangle((x,y,x+9,y+9),fill=(20,35,50))
            im.save(p)
            report=audit_feedback_images(folder,Path(path)/"report.json")
            self.assertFalse(report["all_four_indicators_valid"])
            self.assertEqual(report["records"][0]["text_white_pixels"],0)

    def test_invalid_desktop_dimensions_fail(self):
        with tempfile.TemporaryDirectory() as path:
            folder=synthetic(Path(path)/"feedback")
            Image.new("RGB",(600,450),(40,55,66)).save(folder/"load-event.png")
            with self.assertRaises(ValueError):
                audit_feedback_images(folder,Path(path)/"report.json")


if __name__ == "__main__":
    unittest.main()
