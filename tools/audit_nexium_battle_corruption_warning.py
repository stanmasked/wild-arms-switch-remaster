#!/usr/bin/env python3
"""Stage370: audit actual opt-in corruption banner on two real NeXium boots.

This tests on-screen warning visibility; independent Stage369 evidence is
responsible for verifying that both damaged WABJ copies remain untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import ImageChops

from audit_nexium_checkpoints import screen_point
from audit_nexium_field_journal import read_rgb, native_pixel

RED = (201, 67, 76)
WHITE = (246, 247, 252)
PANEL = (31, 45, 66)
GOLD = (245, 183, 66)
BANNER_RECT = (*screen_point(690, 554), *screen_point(1240, 609))

HELD = ("00_twentythird_zero_after_corruption",
        "02_twentythird_volatile_retreat",
        "03_twentyfourth_zero_after_reboot",
        "05_twentyfourth_volatile_retreat")
IDLE = ("01_twentythird_after_retreat",
        "04_twentyfourth_after_retreat")
SAMPLES = ((690, 554, RED), (695, 559, PANEL), (711, 565, WHITE),
           (711, 585, RED), (1239, 606, RED))


def banner(frame):
    return all(native_pixel(frame, x, y) == rgb for x, y, rgb in SAMPLES)


def same_banner(a, b):
    return ImageChops.difference(
        a.crop(BANNER_RECT), b.crop(BANNER_RECT)).getbbox() is None


def audit_warning(folder, good_rewards, output):
    root = Path(folder)
    required = {n + ".png" for n in HELD + IDLE}
    found = {p.name for p in root.glob("*.png")}
    if required != found:
        raise ValueError(f"unexpected/missing NeXium guest PNG: {sorted(required ^ found)}")
    images = {n: read_rgb(root / (n + ".png")) for n in HELD + IDLE}
    good = read_rgb(good_rewards)
    checks = {
        "twentythird_initial_ZL_shows_corrupt_A_B_notice":
            banner(images[HELD[0]]),
        "twentythird_volatile_ZL_keeps_notice":
            banner(images[HELD[1]]),
        "twentyfourth_independent_boot_shows_notice_again":
            banner(images[HELD[2]]),
        "twentyfourth_volatile_ZL_keeps_notice":
            banner(images[HELD[3]]),
        "both_normal_B_return_frames_have_no_warning":
            not banner(images[IDLE[0]]) and not banner(images[IDLE[1]]),
        "prior_valid_four_win_reward_panel_has_no_warning":
            not banner(good),
        "banner_static_through_both_processes":
            all(same_banner(images[HELD[0]], images[n]) for n in HELD[1:]),
        "prior_ZL_results_outline_uncovered":
            all(native_pixel(images[n], 690, 612) == GOLD for n in HELD),
    }
    result = {
        "kind": "stage370_real_guest_explicit_both_CRC_invalid_warning",
        "scope": "read_only_held_ZL_without_storage_mutation",
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "sha256": {
            **{name: hashlib.sha256((root / (name + ".png")).read_bytes()).hexdigest()
               for name in HELD + IDLE},
            "valid_prior_rewards": hashlib.sha256(
                Path(good_rewards).read_bytes()).hexdigest(),
        },
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screens", required=True)
    parser.add_argument("--prior-valid-rewards", required=True)
    parser.add_argument("--output", required=True)
    a = parser.parse_args()
    try:
        result = audit_warning(a.screens, a.prior_valid_rewards, a.output)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"Stage370 warning audit rejected: {exc}\n")
    print(json.dumps(result["checks"], sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1, "NeXium warning was absent or incorrectly drawn\n")
