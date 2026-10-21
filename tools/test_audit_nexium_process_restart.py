#!/usr/bin/env python3
"""Strict negative/positive invented screens for guest restart auditor."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from audit_field_capture import NAMES
from audit_nexium_checkpoints import VIEW_X, VIEW_W, VIEW_H, SCREEN_SIZE, screen_point
from audit_nexium_storage_feedback import (
    projected_notice, SD_LOADED_COLOR
)
from test_audit_nexium_checkpoints import refs, desktop
from audit_nexium_process_restart import check_restart


def fixture(directory):
    root=Path(directory)
    reference=root/"reference"
    refs(reference)
    shots=root/"restart"
    shots.mkdir()
    first=root/"first-event.png"
    desktop(reference/(NAMES[0]+".png")).save(shots/"01_fresh_process_start.png")
    shot=desktop(reference/(NAMES[1]+".png"))
    shot.save(shots/"03_restored_pending_event.png")
    shot.save(first)
    screen=desktop(reference/(NAMES[1]+".png"))
    notice=projected_notice(SD_LOADED_COLOR).convert("RGB")
    # Insert only the plaque pixels, do not overwrite the field viewport.
    x0,y0=screen_point(982,29)
    x1,y1=screen_point(1252,80)
    native_x0=x0-VIEW_X
    screen.paste(notice.crop((native_x0,y0,x1-VIEW_X,y1)),(x0,y0))
    screen.save(shots/"02_sd_loaded_notice.png")
    before=root/"first-notice.json"
    before.write_text(json.dumps({
        "all_four_indicators_valid":True,
        "records":[{"phase": "unused"}]*2 +
            [{"phase":"save-event","notice":"sd_saved"},
             {"phase":"load-event","notice":"ram_loaded"}]}))
    meta=root/"processes.json"
    meta.write_text(json.dumps({
        "first_pid":123,"second_pid":456,
        "first_wait_completed":True,
        "same_emulator_data_root":True}))
    return reference,shots,before,first,meta,root/"report.json"


class RestartAuditTests(unittest.TestCase):
    def test_two_independent_processes_restored(self):
        with tempfile.TemporaryDirectory() as d:
            report=check_restart(*fixture(d))
            self.assertTrue(report["all_checks_passed"])
            self.assertEqual(report["notice_rgb_mismatches"],0)

    def test_wrong_badge_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(d)
            photo=args[1]/"02_sd_loaded_notice.png"
            with Image.open(photo) as original:
                im=original.convert("RGB")
            px=screen_point(1008,54)
            im.putpixel(px,(104,149,244))  # RAM LOADED, not SD LOADED
            im.save(photo)
            report=check_restart(*args)
            self.assertFalse(report["all_checks_passed"])

    def test_pid_identity_and_missing_first_proof_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(d)
            p=args[4]
            data=json.loads(p.read_text())
            data["second_pid"]=data["first_pid"]
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                check_restart(*args)
        with tempfile.TemporaryDirectory() as d:
            args=fixture(d)
            args[2].write_text(json.dumps({"records":[]}))
            with self.assertRaises(ValueError):
                check_restart(*args)

    def test_wrong_restored_game_and_tampered_first_frame_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            args=fixture(d)
            with Image.open(args[1]/"01_fresh_process_start.png") as original:
                im=original.convert("RGB")
            im.putpixel((340,300),(18,38,201))
            im.save(args[1]/"01_fresh_process_start.png")
            self.assertFalse(check_restart(*args)["all_checks_passed"])
        with tempfile.TemporaryDirectory() as d:
            args=fixture(d)
            with Image.open(args[1]/"03_restored_pending_event.png") as original:
                im=original.convert("RGB")
            im.putpixel((340,300),(18,38,201))
            im.save(args[1]/"03_restored_pending_event.png")
            self.assertFalse(check_restart(*args)["all_checks_passed"])


if __name__=="__main__":
    unittest.main()
