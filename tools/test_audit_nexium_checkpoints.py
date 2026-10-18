#!/usr/bin/env python3
"""Deterministic fake-desktop images for real screenshot checkpoint selector."""
from pathlib import Path
import json
import tempfile
import unittest

from PIL import Image, ImageDraw
from audit_field_capture import NAMES, WIDTH, HEIGHT, EXPECTED_BARS, make_png
from audit_nexium_checkpoints import (audit_sequence, inspect_frame,
                                      load_references, SCREEN_SIZE)


def refs(root):
    import hashlib
    root.mkdir()
    manifest = {
        "kind": "host_reference_not_emulator_capture",
        "width": WIDTH, "height": HEIGHT,
        "round_trip_pixels_equal": True, "frames": []
    }
    names = list(NAMES)
    centers = ((384,232), (576,232), (704,488),
               (384,232), (384,232))
    for i, (name, (cx, cy)) in enumerate(zip(names, centers)):
        image = Image.new("RGB", (WIDTH, HEIGHT),
                          (19,34,38) if i == 3 else (14,20,34))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0,0,1279,9), fill=EXPECTED_BARS[i])
        for row in range(7):
            for col in range(11):
                x, y = 288+col*64, 136+row*64
                floor = ((col+row)%3) != 0
                colour = (174,155,115) if floor else (47,68,87)
                if i == 3 and (col, row) == (4,1):
                    colour = (245,183,66)
                draw.rectangle((x+1,y+1,x+62,y+62), fill=colour)
        col = (cx-320)//64
        row = (cy-168)//64
        tile_x,tile_y = 288+col*64,136+row*64
        draw.rectangle((tile_x+1,tile_y+1,tile_x+62,tile_y+62),
                       fill=(174,155,115))
        shade=(246,246,246) if i in (1,2) else (201,67,76)
        draw.rectangle((cx-19,cy-19,cx+18,cy+18),fill=shade)
        draw.rectangle((cx+10,cy-5,cx+19,cy+4),fill=(22,27,42))
        manifest["frames"].append({
            "scene": name,
            "png_sha256": None, "raw_rgb_sha256": None,
            "status_rgb": list(EXPECTED_BARS[i])
        })
        rgb = image.tobytes()
        raw = make_png(rgb)
        (root/(name+".png")).write_bytes(raw)
        manifest["frames"][-1]["png_sha256"]=hashlib.sha256(raw).hexdigest()
        manifest["frames"][-1]["raw_rgb_sha256"]=hashlib.sha256(rgb).hexdigest()
    (root/"capture_manifest.json").write_text(json.dumps(manifest))


def desktop(ref):
    # Reproduce the exact Xvfb native-view scaling observed in stage 288.
    background = Image.new("RGB", SCREEN_SIZE, (15,15,17))
    with Image.open(ref) as raw:
        patch = raw.convert("RGB").resize((1234,694), Image.Resampling.NEAREST)
        background.paste(patch,(23,0))
    return background


class CheckpointsTests(unittest.TestCase):
    def test_all_five_in_order_succeeds_and_writes_raw_selected_screens(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/"refs"
            refs(ref)
            initial=root/"start.png"
            desktop(ref/(NAMES[0]+".png")).save(initial)
            timeline=root/"timeline"
            timeline.mkdir()
            # 20+ timeline files; several duplicates between checkpoints.
            states=[0]*5 + [1]*5 + [2]*5 + [3]*5 + [4]*5
            for i, stage in enumerate(states):
                desktop(ref/(NAMES[stage]+".png")).save(
                    timeline/f"frame-{i:02}.png")
            result=audit_sequence(ref,initial,timeline,root/"report.json",
                                  root/"selected")
            self.assertTrue(result["full_five_checkpoint_sequence_observed"])
            self.assertEqual([x["scene"] for x in result["verified_scenes"]],
                             list(NAMES))
            self.assertEqual(len(list((root/"selected").glob("*.png"))), 5)
            self.assertFalse(result["pixel_perfect_1280x720_parity_verified"])

    def test_missing_area1_never_passes_and_never_labels_ghost_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/"refs"
            refs(ref)
            initial=root/"start.png"
            desktop(ref/(NAMES[0]+".png")).save(initial)
            timeline=root/"timeline"
            timeline.mkdir()
            for i in range(25):
                stage=(1 if i<10 else 2 if i<15 else 4)
                desktop(ref/(NAMES[stage]+".png")).save(
                    timeline/f"frame-{i:02}.png")
            output=root/"selected"
            result=audit_sequence(ref,initial,timeline,root/"report.json",output)
            self.assertFalse(result["full_five_checkpoint_sequence_observed"])
            self.assertEqual([x["scene"] for x in result["verified_scenes"]],
                             list(NAMES[:3]))
            self.assertFalse(output.exists())

    def test_manifest_hash_failure_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/"refs"
            refs(ref)
            target=ref/(NAMES[0]+".png")
            target.write_bytes(target.read_bytes()+b"tampered")
            with self.assertRaises(ValueError):
                load_references(ref)

    def test_blank_or_wrong_status_never_matches_even_if_colours_elsewhere(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ref=root/"refs"
            refs(ref)
            expected=load_references(ref)[1]
            screenshot=root/"blank.png"
            Image.new("RGB",SCREEN_SIZE,(0,0,0)).save(screenshot)
            self.assertFalse(inspect_frame(screenshot,expected)["matched"])


if __name__ == "__main__":
    unittest.main()
