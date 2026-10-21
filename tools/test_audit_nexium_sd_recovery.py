#!/usr/bin/env python3
"""Synthetic pixel and CRC fault fixtures for Stage-299 guest SD audit."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from PIL import Image

from audit_field_capture import NAMES
from audit_nexium_checkpoints import VIEW_X, screen_point
from audit_nexium_storage_feedback import projected_notice
from audit_nexium_sd_recovery import (
    SD_WARN_COLOR, slots, valid_slot, damage_latest, audit_recovery
)
from test_audit_nexium_checkpoints import refs, desktop


def journal(generation, filler):
    payload = bytearray(b"WAJ1" + generation.to_bytes(8,"little") +
                        bytes([filler]) * 40)
    payload.extend(zlib.crc32(payload).to_bytes(4,"little"))
    return bytes(payload)


def fixture(root):
    root = Path(root)
    data_root = root / "NeXium"
    a, b = slots(data_root)
    a.parent.mkdir(parents=True)
    a.write_bytes(journal(1,7))
    b.write_bytes(journal(2,9))
    manifest=root/"fault.json"
    damage_latest(data_root,manifest)
    reference=root/"refs"
    refs(reference)
    screens=root/"guest"
    screens.mkdir()
    desktop(reference/(NAMES[0]+".png")).save(
        screens/"01_fresh_process_start.png")
    desktop(reference/(NAMES[0]+".png")).save(
        screens/"03_fallback_initial_state.png")
    image=desktop(reference/(NAMES[0]+".png"))
    projection=projected_notice(SD_WARN_COLOR,label="SD WARN")
    x0,y0=screen_point(982,29)
    x1,y1=screen_point(1252,80)
    image.paste(projection.crop((x0-VIEW_X,y0,x1-VIEW_X,y1)),(x0,y0))
    image.save(screens/"02_sd_warn_notice.png")
    process=root/"processes.json"
    process.write_text(json.dumps({
        "second_pid":120,"third_pid":130,
        "second_wait_completed":True,
        "same_emulator_data_root":True}))
    return (reference,screens,data_root,manifest,process,root/"report.json")


class SdRecoveryAuditTests(unittest.TestCase):
    def test_fault_injection_keeps_a_and_corrupts_b(self):
        with tempfile.TemporaryDirectory() as td:
            a,b=slots(Path(td))
            a.parent.mkdir(parents=True)
            a.write_bytes(journal(1,7))
            b.write_bytes(journal(2,9))
            unchanged=a.read_bytes()
            out=damage_latest(td,Path(td)/"fault.json")
            self.assertTrue(valid_slot(a.read_bytes()))
            self.assertFalse(valid_slot(b.read_bytes()))
            self.assertEqual(a.read_bytes(),unchanged)
            self.assertEqual(out["damaged_generation"],2)

    def test_correct_guest_warning_and_recovered_scene(self):
        with tempfile.TemporaryDirectory() as td:
            result=audit_recovery(*fixture(td))
            self.assertTrue(result["all_checks_passed"])
            self.assertEqual(result["sd_warn_mismatched_pixels"],0)

    def test_same_color_wrong_words_fails(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            p=args[1]/"02_sd_warn_notice.png"
            image=desktop(args[0]/(NAMES[0]+".png"))
            projection=projected_notice(SD_WARN_COLOR,label="RAM ONLY")
            x0,y0=screen_point(982,29)
            x1,y1=screen_point(1252,80)
            image.paste(projection.crop((x0-VIEW_X,y0,x1-VIEW_X,y1)),(x0,y0))
            image.save(p)
            report=audit_recovery(*args)
            self.assertFalse(report["all_checks_passed"])
            self.assertGreater(report["sd_warn_mismatched_pixels"],0)

    def test_modified_healthy_slot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            a,_=slots(args[2])
            b=bytearray(a.read_bytes())
            b[24]^=0x80
            a.write_bytes(b)
            with self.assertRaises(ValueError):
                audit_recovery(*args)

    def test_missing_provenance_or_wrong_generation_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            args=fixture(td)
            v=json.loads(args[4].read_text())
            v["third_pid"]=v["second_pid"]
            args[4].write_text(json.dumps(v))
            with self.assertRaises(ValueError):
                audit_recovery(*args)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            a,b=slots(root)
            a.parent.mkdir(parents=True)
            a.write_bytes(journal(1,1))
            b.write_bytes(journal(3,2))
            with self.assertRaises(ValueError):
                damage_latest(root,root/"fault.json")


if __name__=="__main__":
    unittest.main()
