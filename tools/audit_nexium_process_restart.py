#!/usr/bin/env python3
"""Fail-closed, real guest two-process SD save/load screenshot verification.

A fresh NeXium process must load an event saved by a *previous, terminated*
NeXium process. Reject RAM-only restores, missing provenance, and mismatched
host references. The guest emulator data root remains unchanged between
processes; the C++ game FieldRuntime is newly initialized from scratch.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from audit_field_capture import NAMES
from audit_nexium_checkpoints import load_references, GAME_ROI, SCREEN_SIZE
from audit_nexium_pixel_parity import compare_scene
from audit_nexium_storage_feedback import (
    projected_notice, RESTART_COLORS, VIEW_X, GAME_ROI as PLAQUE_ROI
)

REQUIRED = ("01_fresh_process_start", "02_sd_loaded_notice",
            "03_restored_pending_event")
SD_LOADED = (73, 181, 225)


def check_restart(reference, screenshots, first_notice_json, first_saved,
                  processes, output):
    reference, screenshots = Path(reference), Path(screenshots)
    first_notice_json, first_saved = Path(first_notice_json), Path(first_saved)
    processes, output = Path(processes), Path(output)
    load_references(reference)
    if {p.name for p in screenshots.glob("*.png")} != {
            name + ".png" for name in REQUIRED}:
        raise ValueError("wrong independent guest restart screenshot set")

    first = json.loads(first_notice_json.read_text())
    if (first.get("all_four_indicators_valid") is not True or
        len(first.get("records", [])) != 4 or
        first["records"][2].get("phase") != "save-event" or
        first["records"][2].get("notice") != "sd_saved"):
        raise ValueError("first process did not visibly confirm SD event save")

    proof = json.loads(processes.read_text())
    if (proof.get("first_pid", 0) <= 0 or
        proof.get("second_pid", 0) <= 0 or
        proof["first_pid"] == proof["second_pid"] or
        proof.get("same_emulator_data_root") is not True or
        proof.get("first_wait_completed") is not True):
        raise ValueError("not two distinct completed/started emulator processes")

    initial = compare_scene(reference / (NAMES[0] + ".png"),
                            screenshots / (REQUIRED[0] + ".png"))
    restored = compare_scene(reference / (NAMES[1] + ".png"),
                             screenshots / (REQUIRED[2] + ".png"))
    # Independent first-run screenshot must also be exact scene 1, not just
    # a forged status screenshot. Comparison excludes only the known host HUD.
    saved = compare_scene(reference / (NAMES[1] + ".png"), first_saved)
    with Image.open(screenshots / (REQUIRED[1]+".png")) as im:
        im.load()
        if im.size != SCREEN_SIZE:
            raise ValueError("invalid second-process desktop dimensions")
        rgb = im.convert("RGB")
        accent = rgb.getpixel(
            (VIEW_X + round(1008 * 1234 / 1280), round(54 * 694 / 720)))
        crop = rgb.crop(PLAQUE_ROI)
        expected = projected_notice(SD_LOADED).crop((
            PLAQUE_ROI[0]-VIEW_X, PLAQUE_ROI[1],
            PLAQUE_ROI[2]-VIEW_X, PLAQUE_ROI[3]))
        diff = ImageChops.difference(crop, expected)
        channels = diff.split()
        mask = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),
                                 channels[2])
        mismatches = crop.width*crop.height - mask.histogram()[0]

    ok = (initial["exact_visible_rgb_match"] and
          saved["exact_visible_rgb_match"] and
          restored["exact_visible_rgb_match"] and
          accent == SD_LOADED and mismatches == 0 and
          SD_LOADED in RESTART_COLORS)
    report = {
        "kind": "nexium_separate_process_persistent_sd_checkpoint",
        "provenance": "two_guest_os_processes_same_data_root_xvfb_rgb",
        "hardware_sd_power_cut_test": False,
        "distinct_emulator_processes": True,
        "first_process_sd_saved": True,
        "fresh_runtime_looks_like_area0_start": initial["exact_visible_rgb_match"],
        "saved_event_matches_reference": saved["exact_visible_rgb_match"],
        "second_process_sd_loaded_exact_plaque": accent == SD_LOADED and mismatches == 0,
        "second_process_event_matches_reference": restored["exact_visible_rgb_match"],
        "notice_rgb_mismatches": mismatches,
        "visible_game_pixels_compared": (
            initial["visible_pixels_compared"] +
            saved["visible_pixels_compared"] +
            restored["visible_pixels_compared"]),
        "all_checks_passed": ok,
        "screenshots": {
            name: hashlib.sha256((screenshots / (name + ".png")).read_bytes()).hexdigest()
            for name in REQUIRED
        }
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("reference","screenshots","first-notice-json",
                 "first-saved","processes","output"):
        parser.add_argument("--"+name, type=Path, required=True)
    v=parser.parse_args()
    try:
        answer=check_restart(v.reference,v.screenshots,
                             v.first_notice_json,v.first_saved,
                             v.processes,v.output)
    except (OSError,ValueError,TypeError,KeyError,IndexError) as e:
        parser.exit(2,"Guest restart audit rejected: "+str(e)+"\n")
    print(json.dumps({
        "independent_process_sd_restoration":answer["all_checks_passed"],
        "notice_rgb_mismatches":answer["notice_rgb_mismatches"],
        "pixels_compared":answer["visible_game_pixels_compared"]
    },sort_keys=True))
    if not answer["all_checks_passed"]:
        parser.exit(1,"Different guest process failed SD restore verification\n")


if __name__=="__main__":
    main()
