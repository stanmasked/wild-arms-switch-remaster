#!/usr/bin/env python3
"""Independent invented evidence for repair/restart auditor."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from audit_field_capture import NAMES
from audit_nexium_checkpoints import VIEW_X, screen_point
from audit_nexium_storage_feedback import projected_notice,SD_LOADED_COLOR
from audit_nexium_sd_recovery import SD_WARN_COLOR,slots
from audit_nexium_sd_repair import audit_repair, FOURTH, FIFTH, GREEN
from test_audit_nexium_sd_recovery import journal
from test_audit_nexium_checkpoints import refs,desktop
from audit_nexium_sd_recovery import damage_latest


def photo(reference, path, status=None):
    screen=desktop(reference/(NAMES[0]+".png"))
    if status:
        color,label=status
        patch=projected_notice(color,label=label)
        x0,y0=screen_point(982,29)
        x1,y1=screen_point(1252,80)
        screen.paste(patch.crop((x0-VIEW_X,y0,x1-VIEW_X,y1)),(x0,y0))
    screen.save(path)


def fixture(directory):
    root=Path(directory)
    sdmc=root/"nexium-data"
    a,b=slots(sdmc)
    a.parent.mkdir(parents=True,exist_ok=True)
    a.write_bytes(journal(1,7))
    b.write_bytes(journal(2,9))
    damaged=root/"damage-manifest.json"
    damage_latest(sdmc,damaged)
    # A guest repaired B with the older A snapshot, in the correct slot.
    b.write_bytes(journal(2,7))
    reference=root/"reference"
    refs(reference)
    fourth=root/"fourth"
    fifth=root/"fifth"
    fourth.mkdir()
    fifth.mkdir()
    for name,status in zip(FOURTH,[
            (SD_WARN_COLOR,"SD WARN"),(GREEN,"SD SAVED"),None]):
        photo(reference,fourth/(name+".png"),status)
    for name,status in zip(FIFTH,[
            None,(SD_LOADED_COLOR,"SD LOADED"),None]):
        photo(reference,fifth/(name+".png"),status)
    processes=root/"processes.json"
    processes.write_text(json.dumps({
        "third_pid":300,"fourth_pid":400,"fifth_pid":500,
        "fourth_wait_completed":True,
        "fifth_wait_completed":True,
        "same_emulator_data_root":True
    }))
    return (reference,fourth,fifth,sdmc,damaged,processes,root/"report.json")


class SdRepairTests(unittest.TestCase):
    def test_repaired_journal_and_fifth_guest_pass(self):
        with tempfile.TemporaryDirectory() as td:
            r=audit_repair(*fixture(td))
            self.assertTrue(r["all_checks_passed"])
            self.assertEqual(sum(r["status_plaque_mismatches"].values()),0)
            self.assertTrue(r["older_generation_unchanged"])

    def test_same_colour_wrong_text_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            photo(args[0],args[1]/(FOURTH[1]+".png"),
                  (GREEN,"SD ERROR"))
            r=audit_repair(*args)
            self.assertFalse(r["all_checks_passed"])
            self.assertGreater(r["status_plaque_mismatches"]["fourth_saved"],0)

    def test_changed_old_or_invalid_new_generation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            a,b=slots(args[3])
            a.write_bytes(journal(1,8))
            with self.assertRaises(ValueError):
                audit_repair(*args)
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            a,b=slots(args[3])
            b.write_bytes(b.read_bytes()[:24])
            with self.assertRaises(ValueError):
                audit_repair(*args)

    def test_nonindependent_processes_or_missing_scene_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            data=json.loads(args[5].read_text())
            data["fifth_pid"]=data["fourth_pid"]
            args[5].write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                audit_repair(*args)
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            (args[2]/(FIFTH[2]+".png")).unlink()
            with self.assertRaises(ValueError):
                audit_repair(*args)

    def test_bad_scene_rgb_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            path=args[2]/(FIFTH[2]+".png")
            with Image.open(path) as original:
                img=original.convert("RGB")
            img.putpixel((340,300),(19,61,240))
            img.save(path)
            self.assertFalse(audit_repair(*args)["all_checks_passed"])


if __name__=="__main__":
    unittest.main()
