#!/usr/bin/env python3
"""Stage 299: real NeXium SDMC damage, third-process recovery evidence.

Never uses game ROMs or firmware. Safely changes only the *copied*
synthetic journal B in the per-run isolated emulator data root.
This does NOT simulate physical SD power loss or native hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

from PIL import Image, ImageChops

from audit_field_capture import NAMES
from audit_nexium_checkpoints import load_references, SCREEN_SIZE
from audit_nexium_pixel_parity import compare_scene
from audit_nexium_storage_feedback import (
    WHITE, GAME_ROI, VIEW_X, projected_notice
)

SD_WARN_COLOR = (244, 178, 64)
SCREENS = ("01_fresh_process_start", "02_sd_warn_notice",
           "03_fallback_initial_state")


def hexhash(data):
    return hashlib.sha256(data).hexdigest()


def slots(data_root):
    folder = Path(data_root) / "sdmc" / "switch" / "wild_arms_field"
    return folder / "field-save.a", folder / "field-save.b"


def valid_slot(data):
    return (len(data) == 56 and data[:4] == b"WAJ1" and
            int.from_bytes(data[4:12], "little") > 0 and
            zlib.crc32(data[:52]) == int.from_bytes(data[52:56], "little"))


def damage_latest(data_root, output):
    a, b = slots(data_root)
    # Do not create or probe unrelated emulator files.
    oldest = a.read_bytes()
    newest = b.read_bytes()
    if not valid_slot(oldest) or not valid_slot(newest):
        raise ValueError("SDMC journal does not contain two intact generations")
    ga = int.from_bytes(oldest[4:12], "little")
    gb = int.from_bytes(newest[4:12], "little")
    if (ga, gb) != (1, 2):
        raise ValueError("unexpected generations; refusing SD corruption")
    tampered = bytearray(newest)
    tampered[23] ^= 0x80  # mutate payload without repairing outer CRC
    b.write_bytes(tampered)
    if (not valid_slot(a.read_bytes()) or valid_slot(b.read_bytes()) or
        a.read_bytes() != oldest or b.read_bytes() != tampered):
        raise ValueError("SDMC journal corruption preflight failed")
    manifest = {
        "kind": "nexium_emulated_sdmc_one_slot_crc_corruption",
        "original_slot_a_sha256": hexhash(oldest),
        "original_slot_b_sha256": hexhash(newest),
        "tampered_slot_b_sha256": hexhash(tampered),
        "intact_generation": ga,
        "damaged_generation": gb,
        "corruption_offset": 23,
        "old_slot_still_crc_valid": True,
        "new_slot_crc_invalid": True,
        "physical_sd_power_failure_emulated": False
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def audit_recovery(reference, desktop_dir, data_root, manifest_path,
                   process_manifest_path, output):
    reference, desktop_dir = Path(reference), Path(desktop_dir)
    load_references(reference)
    manifest = json.loads(Path(manifest_path).read_text())
    process = json.loads(Path(process_manifest_path).read_text())
    if (manifest.get("kind") !=
            "nexium_emulated_sdmc_one_slot_crc_corruption" or
        manifest.get("intact_generation") != 1 or
        manifest.get("damaged_generation") != 2 or
        manifest.get("old_slot_still_crc_valid") is not True or
        manifest.get("new_slot_crc_invalid") is not True or
        manifest.get("physical_sd_power_failure_emulated") is not False):
        raise ValueError("untrusted damaged-journal manifest")
    if (not isinstance(process.get("second_pid"), int) or
        not isinstance(process.get("third_pid"), int) or
        process["second_pid"] <= 0 or process["third_pid"] <= 0 or
        process["second_pid"] == process["third_pid"] or
        process.get("second_wait_completed") is not True or
        process.get("same_emulator_data_root") is not True):
        raise ValueError("third NeXium run not independent")
    a, b = slots(data_root)
    original_a = a.read_bytes()
    broken_b = b.read_bytes()
    if (hexhash(original_a) != manifest["original_slot_a_sha256"] or
        hexhash(broken_b) != manifest["tampered_slot_b_sha256"] or
        not valid_slot(original_a) or valid_slot(broken_b)):
        raise ValueError("emulated SDMC bytes changed after injected fault")
    if {p.name for p in desktop_dir.glob("*.png")} != {
            name + ".png" for name in SCREENS}:
        raise ValueError("missing/extra guest warning screenshot")
    fresh = compare_scene(reference / (NAMES[0]+".png"),
                          desktop_dir / (SCREENS[0]+".png"))
    recovered = compare_scene(reference / (NAMES[0]+".png"),
                              desktop_dir / (SCREENS[2]+".png"))
    with Image.open(desktop_dir / (SCREENS[1]+".png")) as im:
        im.load()
        if im.size != SCREEN_SIZE:
            raise ValueError("invalid guest Xvfb screenshot dimensions")
        rgb = im.convert("RGB")
        observed = rgb.crop(GAME_ROI)
        expected = projected_notice(SD_WARN_COLOR, label="SD WARN").crop((
            GAME_ROI[0]-VIEW_X, GAME_ROI[1],
            GAME_ROI[2]-VIEW_X, GAME_ROI[3]))
        delta = ImageChops.difference(observed, expected).split()
        maximum = ImageChops.lighter(ImageChops.lighter(delta[0],delta[1]),
                                      delta[2])
        mismatches = observed.width * observed.height - maximum.histogram()[0]
    result = {
        "kind": "nexium_third_guest_process_recovers_intact_sd_generation",
        "guest_source": "actual_ne_xium_xvfb_screenshots",
        "sdmc_journal_a_crc_valid": True,
        "sdmc_journal_b_crc_invalid": True,
        "third_process_independent": True,
        "fresh_start_exact_visible_rgb": fresh["exact_visible_rgb_match"],
        "fallback_to_initial_exact_visible_rgb": recovered["exact_visible_rgb_match"],
        "sd_warn_plaque_exact_rgb": mismatches == 0,
        "sd_warn_mismatched_pixels": mismatches,
        "game_pixels_compared": fresh["visible_pixels_compared"] +
                                recovered["visible_pixels_compared"],
        "all_checks_passed": (fresh["exact_visible_rgb_match"] and
                              recovered["exact_visible_rgb_match"] and
                              mismatches == 0),
        "screenshots_sha256": {
            n: hexhash((desktop_dir / (n + ".png")).read_bytes())
            for n in SCREENS
        },
        "physical_switch_tested": False
    }
    output=Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2,sort_keys=True)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    prepare=sub.add_parser("inject")
    prepare.add_argument("--data-root",required=True,type=Path)
    prepare.add_argument("--manifest",required=True,type=Path)
    verify=sub.add_parser("verify")
    for name in ("reference","screenshots","data-root","manifest","processes","output"):
        verify.add_argument("--"+name,required=True,type=Path)
    v=parser.parse_args()
    try:
        if v.command=="inject":
            report=damage_latest(v.data_root,v.manifest)
        else:
            report=audit_recovery(v.reference,v.screenshots,v.data_root,
                                  v.manifest,v.processes,v.output)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        parser.exit(2,"SD recovery audit rejected: "+str(exc)+"\n")
    print(json.dumps(report,sort_keys=True))
    if v.command=="verify" and not report["all_checks_passed"]:
        parser.exit(1,"NeXium failed to show exact fallback scene and SD WARN\n")


if __name__=="__main__":
    main()
