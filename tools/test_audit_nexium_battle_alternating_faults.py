#!/usr/bin/env python3
"""ROM-free synthetic positive/negative tests; not emulator guest evidence."""
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from audit_nexium_checkpoints import screen_point
from audit_nexium_battle_alternating_faults import (
    audit_alternating, GLYPH, GREEN, GOLD, PANEL,
)
from test_audit_nexium_battle_post_crc_victory import fixture as prev_fixture, make_three_win_panel
from test_audit_nexium_battle_two_victories import picture, journal


def paint_digit(img, x, y, digit, ink):
    for row, mask in enumerate(GLYPH[digit]):
        for col in range(5):
            img.putpixel(screen_point(x + 2 * col + 1, y + 2 * row + 1),
                         ink if ((mask >> (4-col)) & 1) else PANEL)


def four_panel():
    image = make_three_win_panel()
    for x, y, digit, color in ((776, 650, 4, GOLD),
                                (1013, 623, 3, GREEN), (1026, 623, 2, GREEN),
                                (1091, 623, 4, GREEN), (1104, 623, 8, GREEN)):
        paint_digit(image, x, y, digit, color)
    return image


def damage(original, target):
    raw = bytearray(Path(original).read_bytes())
    raw[48] ^= 0x80
    Path(target).write_bytes(raw)


def make_case(folder):
    root = Path(folder)
    prev = prev_fixture(root)
    # stage367 saved generation 5 A / generation 4 B (real world source is SDMC).
    shots = root / "stage368"
    shots.mkdir()
    names = (
        "00_twentieth_fallback_three", "01_twentieth_fourth_victory",
        "02_twentieth_four_rewards", "03_twentyfirst_reload_four",
        "04_twentyfirst_after_retreat", "05_twentyfirst_retreat_panel",
        "06_twentysecond_fallback_four", "07_twentysecond_after_retreat",
        "08_twentysecond_repair_panel",
    )
    three = make_three_win_panel()
    four = four_panel()
    for name in (names[0],):
        three.save(shots / (name + ".png"))
    picture("01_first_victory").save(shots / (names[1] + ".png"))
    for name in (names[2], names[3], names[5], names[6], names[8]):
        four.save(shots / (name + ".png"))
    for name in (names[4], names[7]):
        picture("07_third_retreat").save(shots / (name + ".png"))
    known_three = root / "stage367-known-three.png"
    three.save(known_three)
    names = ("base5.a", "base4.b", "damaged5.a",
             "after20.a", "after20.b", "after21.a", "after21.b",
             "damaged6.b", "after22.a", "after22.b")
    files = [root / name for name in names]
    # prev[7] = valid generation-5 A, prev[8] = generation-4 B.
    shutil.copyfile(prev[7], files[0])
    shutil.copyfile(prev[8], files[1])
    damage(files[0], files[2])
    journal(files[3], 5, 1, 4, 1, 32, 48)
    shutil.copyfile(files[1], files[4])
    shutil.copyfile(files[3], files[5])
    journal(files[6], 6, 3, 4, 2, 32, 48)
    damage(files[6], files[7])
    shutil.copyfile(files[5], files[8])
    shutil.copyfile(files[6], files[9])
    pids_new = root / "twentieth-through-twentysecond.txt"
    pids_new.write_text("twentieth 1007\ntwentyfirst 1008\ntwentysecond 1009\n",
                        encoding="ascii")
    keys = root / "keys368.log"
    events = ([("twentieth", "x"), ("twentieth", "e")]
              + [("twentieth", "c")] * 7
              + [("twentieth", "x"), ("twentyfirst", "x"),
                 ("twentyfirst", "e"), ("twentyfirst", "x"),
                 ("twentysecond", "x"), ("twentysecond", "e"),
                 ("twentysecond", "x")])
    keys.write_text("".join(f"{name} 2026-10-20T16:00:00Z {key}\n"
                            for name, key in events), encoding="ascii")
    # previous fixture's source image is an original field frame (no overlay).
    return (
        shots, prev[1], known_three,
        files[0], files[1], files[2], files[3], files[4],
        files[5], files[6], files[7], files[8], files[9],
        prev[9], prev[10], prev[11], pids_new, keys, root / "stage368-report.json",
    )


class AlternatingJournalFaultTests(unittest.TestCase):
    def test_valid_two_independent_faults_and_fourth_win(self):
        with tempfile.TemporaryDirectory() as d:
            r = audit_alternating(*make_case(d))
            self.assertTrue(r["all_checks_passed"], r["checks"])
            self.assertEqual(len(r["checks"]), 17)

    def test_absent_png_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            (a[0] / "06_twentysecond_fallback_four.png").unlink()
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_extra_png_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            picture("00_first_manual").save(a[0] / "fake.png")
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_one_byte_crc_fault_provenance_rejects_payload_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            raw = bytearray(a[5].read_bytes())
            raw[21] ^= 1
            a[5].write_bytes(raw)
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_valid_unmodified_B_rejected_as_fault(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            shutil.copyfile(a[9], a[10])
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_fourth_victory_image_required(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            picture("00_first_manual").save(a[0] / "01_twentieth_fourth_victory.png")
            self.assertFalse(audit_alternating(*a)["checks"][
                "twentieth_guest_seven_real_A_edges_reach_fourth_victory"])

    def test_four_win_panel_digits_not_third_win(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            make_three_win_panel().save(a[0] / "02_twentieth_four_rewards.png")
            self.assertFalse(audit_alternating(*a)["checks"][
                "twentieth_guest_renders_four_wins_32EXP_48Gella"])

    def test_fourth_victory_cannot_double_credit(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[6], 5, 1, 4, 1, 40, 60)
            self.assertFalse(audit_alternating(*a)["checks"][
                "first_repair_of_A_records_new_victory_as_gen5_not_duplicate_retreat"])

    def test_old_B_must_be_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[7], 4, 1, 3, 1, 25, 36)
            self.assertFalse(audit_alternating(*a)["checks"][
                "first_repair_preserves_old_gen4_B_bit_for_bit"])

    def test_fresh_twentyfirst_reload_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            make_three_win_panel().save(a[0] / "03_twentyfirst_reload_four.png")
            self.assertFalse(audit_alternating(*a)["checks"][
                "twentyfirst_guest_loads_same_four_win_panel_in_fresh_process"])

    def test_second_retreat_must_not_pay_again(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[9], 6, 3, 4, 2, 40, 60)
            damage(a[9], a[10])
            self.assertFalse(audit_alternating(*a)["checks"][
                "second_save_to_B_records_gen6_without_extra_rewards"])

    def test_after_second_repair_A_must_remain_exact(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[11], 5, 1, 4, 1, 33, 48)
            self.assertFalse(audit_alternating(*a)["checks"][
                "second_repair_preserves_A_and_restores_B_bit_for_bit"])

    def test_after_second_repair_B_must_be_identical(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            journal(a[12], 6, 3, 4, 2, 32, 49)
            self.assertFalse(audit_alternating(*a)["checks"][
                "second_repair_preserves_A_and_restores_B_bit_for_bit"])

    def test_second_repair_panel_must_match_retreat_panel(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            make_three_win_panel().save(a[0] / "08_twentysecond_repair_panel.png")
            self.assertFalse(audit_alternating(*a)["checks"][
                "both_retreat_panels_match_after_B_recovery"])

    def test_reused_guest_pid_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            a[16].write_text("twentieth 1005\ntwentyfirst 1008\ntwentysecond 1009\n")
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_fake_repeated_A_edge_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            a[17].write_text(a[17].read_text().replace("Z c\n", "Z e\n", 1))
            with self.assertRaises(ValueError):
                audit_alternating(*a)

    def test_modified_return_field_detected(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_case(d)
            path = a[0] / "07_twentysecond_after_retreat.png"
            with Image.open(path) as im:
                rgb = im.convert("RGB")
            rgb.putpixel(screen_point(600, 350), (20, 200, 80))
            rgb.save(path)
            self.assertFalse(audit_alternating(*a)["checks"][
                "twentysecond_guest_returns_same_map_after_repair"])


if __name__ == "__main__":
    unittest.main()
