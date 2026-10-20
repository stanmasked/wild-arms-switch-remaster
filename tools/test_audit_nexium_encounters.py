#!/usr/bin/env python3
"""Positive/adversarial fixture suite for observed NeXium ZR encounters."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_W, VIEW_H, VIEW_X
from audit_nexium_encounters import (
    NAMES, FIELD_OK, FIELD_EVENT, GOLD, BLUE, RED, DARK, audit_encounter
)

FIELD = (14,20,34)


def screenshot(name):
    native = Image.new("RGB", (1280, 720), FIELD)
    draw = ImageDraw.Draw(native)
    if name in ("02_event_pending",):
        draw.rectangle((0,0,1279,9),fill=FIELD_EVENT)
    else:
        draw.rectangle((0,0,1279,9),fill=FIELD_OK)

    if name not in ("04_encounter_open","05_encounter_strike"):
        if name not in ("00_field_start",):
            draw.rectangle((1240,20,1257,37),fill=GOLD)
        if name=="06_field_return":
            draw.rectangle((495,215,520,240),fill=RED)
        elif name in ("02_event_pending","03_event_acknowledged"):
            draw.rectangle((564,215,588,240),fill=RED)
        else:
            draw.rectangle((372,215,396,240),fill=RED)
    else:
        draw.rectangle((0,0,1279,719),fill=DARK)
        draw.rectangle((70,190,73,257),fill=BLUE)
        draw.rectangle((670,165,673,185),fill=GOLD)
        width=340 if name=="04_encounter_open" else 194
        draw.rectangle((692,249,692+width-1,268),fill=RED)
        if name=="05_encounter_strike":
            draw.rectangle((70,284,73,304),fill=BLUE)
    desktop = Image.new("RGB", SCREEN_SIZE)
    desktop.paste(
        native.resize((VIEW_W,VIEW_H),Image.Resampling.NEAREST),
        (VIEW_X,0))
    return desktop


def populate(folder):
    for name in NAMES:
        screenshot(name).save(Path(folder)/(name+".png"))


class EncounterGuestAuditTests(unittest.TestCase):
    def check_mutation(self, name, paint, failed_check):
        with tempfile.TemporaryDirectory() as root:
            populate(root)
            path=Path(root)/(name+".png")
            with Image.open(path) as source:
                edited=source.convert("RGB")
            paint(edited)
            edited.save(path)
            result=audit_encounter(root,Path(root)/"report.json")
            self.assertFalse(result["checks"][failed_check])

    def point(self, x, y):
        return (VIEW_X+round(x*VIEW_W/1280),round(y*VIEW_H/720))

    def test_positive_seven_observations(self):
        with tempfile.TemporaryDirectory() as root:
            populate(root)
            result=audit_encounter(root,Path(root)/"audit.json")
            self.assertTrue(result["all_checks_passed"])
            self.assertEqual(len(result["checks"]),7)
            self.assertEqual(len(result["sha256"]),7)

    def test_hud_occlusion_no_false_negative(self):
        with tempfile.TemporaryDirectory() as root:
            populate(root)
            path=Path(root)/"04_encounter_open.png"
            with Image.open(path) as im:
                desktop=im.convert("RGB")
            ImageDraw.Draw(desktop).rectangle(
                (13,14,238,153),fill=(60,212,92))
            desktop.save(path)
            self.assertTrue(audit_encounter(
                root,Path(root)/"report.json")["all_checks_passed"])

    def test_missing_ZR_toggle_cannot_pass(self):
        self.check_mutation("01_zr_enabled",
          lambda im: im.putpixel(self.point(1245,25),FIELD),
          "ZR_enabled_without_moving_or_mutating_field")

    def test_pending_event_required(self):
        self.check_mutation("02_event_pending",
          lambda im: im.putpixel(self.point(0,5),FIELD_OK),
          "third_tile_paused_field_event_no_premature_battle")

    def test_event_ack_required(self):
        self.check_mutation("03_event_acknowledged",
          lambda im: im.putpixel(self.point(0,5),FIELD_EVENT),
          "A_acknowledges_event_before_any_encounter")

    def test_battle_foe_target_required(self):
        self.check_mutation("04_encounter_open",
          lambda im: im.putpixel(self.point(670,165),FIELD),
          "fourth_real_step_opens_selected_battle")

    def test_strike_hp_change_required(self):
        self.check_mutation("05_encounter_strike",
          lambda im: im.putpixel(self.point(922,249),RED),
          "A_damage_only_inside_battle")

    def test_return_to_moved_position_required(self):
        self.check_mutation("06_field_return",
          lambda im: im.putpixel(self.point(500,220),FIELD),
          "B_returns_to_moved_field_and_keeps_ZR_mode")

    def test_held_world_must_not_move_when_just_toggled(self):
        self.check_mutation("01_zr_enabled",
          lambda im: im.putpixel(self.point(600,280),(2,255,49)),
          "ZR_enabled_without_moving_or_mutating_field")

    def test_missing_and_extra_screenshots_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            populate(root)
            (Path(root)/"04_encounter_open.png").unlink()
            with self.assertRaises(ValueError):
                audit_encounter(root,Path(root)/"report.json")
            screenshot("04_encounter_open").save(Path(root)/"04_encounter_open.png")
            screenshot("04_encounter_open").save(Path(root)/"extra.png")
            with self.assertRaises(ValueError):
                audit_encounter(root,Path(root)/"report.json")


if __name__ == "__main__":
    unittest.main()
