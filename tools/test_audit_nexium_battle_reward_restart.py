#!/usr/bin/env python3
"""Adversarial synthetic oracle fixtures: NOT proof of real NeXium game runs."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image, ImageDraw
from audit_nexium_checkpoints import SCREEN_SIZE, VIEW_X, VIEW_W, VIEW_H, screen_point
from audit_nexium_battle_reward_restart import (
    NAMES, audit_rewards, MAP, GOLD, GREEN, PANEL, DARK,
)

FIELD=(14,20,34)
RED=(201,67,76)


def journal(path, generation, outcome, wins, retreats, exp, gella):
    body=bytearray(36)
    body[:4]=b"WABR"
    body[4]=1
    body[5]=outcome
    for offset,value in ((8,wins),(16,retreats),(20,exp),(24,gella)):
        struct.pack_into("<I",body,offset,value)
    struct.pack_into("<I",body,32,zlib.crc32(body[:32]))
    raw=bytearray(52)
    raw[:4]=b"WABJ"
    struct.pack_into("<Q",raw,4,generation)
    raw[12:48]=body
    struct.pack_into("<I",raw,48,zlib.crc32(raw[:48]))
    Path(path).write_bytes(raw)


def picture(name):
    native=Image.new("RGB",(1280,720),DARK if name=="01_real_victory" else FIELD)
    d=ImageDraw.Draw(native)
    if name=="01_real_victory":
        d.rectangle((319,293,335,305),fill=GREEN)
    else:
        d.rectangle((0,0,1279,9),fill=MAP)
        d.rectangle((340,230,369,250),fill=RED)
        if name in ("02_first_guest_reward_panel","03_reboot_reward_panel"):
            d.rectangle((690,612,1239,707),fill=PANEL)
            d.rectangle((690,612,1239,615),fill=GOLD)
            d.rectangle((779,654,781,658),fill=GOLD) # WINS '1'
            d.rectangle((1014,628,1017,631),fill=GREEN) # EXP 8
            d.rectangle((1079,623,1082,626),fill=GREEN) # G 12 / 1
            d.rectangle((1090,634,1093,637),fill=GREEN) # G 12 / 2
    desktop=Image.new("RGB",SCREEN_SIZE)
    desktop.paste(native.resize((VIEW_W,VIEW_H),Image.Resampling.NEAREST),
                  (VIEW_X,0))
    return desktop


def create_fixture(folder):
    root=Path(folder)
    shots=root/"shots"
    shots.mkdir()
    for name in NAMES:picture(name).save(shots/(name+".png"))
    first,a,b=(root/x for x in ("first.a","final.a","final.b"))
    journal(first,1,1,1,0,8,12)
    journal(a,1,1,1,0,8,12)
    journal(b,2,3,1,1,8,12)
    return shots,first,a,b,root/"audit.json"


class RealGuestRewardAuditorTests(unittest.TestCase):
    def test_positive_five_frames_and_two_valid_reward_records(self):
        with tempfile.TemporaryDirectory() as folder:
            result=audit_rewards(*create_fixture(folder))
            self.assertTrue(result["all_checks_passed"],result["checks"])
            self.assertEqual(len(result["checks"]),8)
            self.assertEqual(len(result["sha256"]),8)

    def test_missing_guest_frame_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            (args[0]/"03_reboot_reward_panel.png").unlink()
            with self.assertRaises(ValueError):audit_rewards(*args)

    def test_extra_guest_frame_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            picture("00_manual_before_win").save(args[0]/"extra.png")
            with self.assertRaises(ValueError):audit_rewards(*args)

    def test_bad_inner_crc_rejected_even_with_valid_outer_crc(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            raw=bytearray(args[3].read_bytes())
            raw[44]^=1
            struct.pack_into("<I",raw,48,zlib.crc32(raw[:48]))
            args[3].write_bytes(raw)
            with self.assertRaises(ValueError):audit_rewards(*args)

    def test_wrong_actual_reward_amount_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            journal(args[3],2,3,1,1,16,24)
            result=audit_rewards(*args)
            self.assertFalse(result["checks"]["next_generation_kept_rewards_and_added_no_duplicated_victory"])

    def test_no_victory_guest_frame_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            picture("00_manual_before_win").save(args[0]/"01_real_victory.png")
            result=audit_rewards(*args)
            self.assertFalse(result["checks"]["real_seven_controller_attacks_produced_victory"])

    def test_reboot_panel_must_match_first_guest(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            picture("00_manual_before_win").save(args[0]/"03_reboot_reward_panel.png")
            result=audit_rewards(*args)
            self.assertFalse(result["checks"]["new_guest_shows_identical_earned_history_before_fighting"])

    def test_return_to_exact_field_not_a_moved_player(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            path=args[0]/"04_reboot_after_retreat.png"
            with Image.open(path) as inp:im=inp.convert("RGB")
            im.putpixel(screen_point(600,350),(33,212,1))
            im.save(path)
            result=audit_rewards(*args)
            self.assertFalse(result["checks"]["second_guest_retreat_returns_to_identical_original_map"])

    def test_original_generation_is_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            journal(args[2],1,1,1,0,9,12)
            result=audit_rewards(*args)
            self.assertFalse(result["checks"]["first_valid_generation_remains_bit_for_bit_unchanged"])

    def test_missing_first_record_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            args=create_fixture(folder)
            args[1].unlink()
            with self.assertRaises(OSError):audit_rewards(*args)


if __name__=="__main__":
    unittest.main()
