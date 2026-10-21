#!/usr/bin/env python3
"""Prove an emulated SDMC journal was repaired by a *fourth* guest and
reloaded by a *fifth* independent NeXium guest process.

Compare both 56-byte committed slot CRCs, generations, unchanged older
slot and projected Xvfb HUD pixels. This does not test hardware SDMC.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

from audit_field_capture import NAMES
from audit_nexium_checkpoints import load_references, SCREEN_SIZE
from audit_nexium_pixel_parity import compare_scene
from audit_nexium_storage_feedback import (
    GAME_ROI, VIEW_X, projected_notice, SD_LOADED_COLOR,
)
from audit_nexium_sd_recovery import SD_WARN_COLOR, slots, valid_slot

GREEN = (56, 207, 125)
FOURTH = ("01_sd_warn_before_repair", "02_sd_saved_after_repair",
          "03_repaired_start_scene")
FIFTH = ("01_fresh_process_start", "02_sd_loaded_notice",
         "03_restored_start_scene")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact_plaque(image_path, color, wording):
    with Image.open(image_path) as im:
        im.load()
        if im.size != SCREEN_SIZE:
            raise ValueError("bad guest desktop dimensions: " + str(image_path))
        observed = im.convert("RGB").crop(GAME_ROI)
        expected = projected_notice(color, label=wording).crop((
            GAME_ROI[0]-VIEW_X, GAME_ROI[1],
            GAME_ROI[2]-VIEW_X, GAME_ROI[3]))
        channels = ImageChops.difference(observed, expected).split()
        maximum = ImageChops.lighter(
            ImageChops.lighter(channels[0], channels[1]), channels[2])
        return observed.width * observed.height - maximum.histogram()[0]


def audit_repair(reference, fourth_screens, fifth_screens, data_root,
                 damage_manifest, process_manifest, output):
    reference=Path(reference)
    fourth_screens=Path(fourth_screens)
    fifth_screens=Path(fifth_screens)
    load_references(reference)
    fault=json.loads(Path(damage_manifest).read_text())
    proc=json.loads(Path(process_manifest).read_text())
    if (fault.get("kind") !=
        "nexium_emulated_sdmc_one_slot_crc_corruption" or
        fault.get("intact_generation") != 1 or
        fault.get("damaged_generation") != 2 or
        fault.get("old_slot_still_crc_valid") is not True or
        fault.get("new_slot_crc_invalid") is not True):
        raise ValueError("invalid prior damage evidence")
    if (not all(isinstance(proc.get(key), int) and proc[key] > 0
                for key in ("third_pid","fourth_pid","fifth_pid")) or
        len({proc["third_pid"], proc["fourth_pid"],
             proc["fifth_pid"]}) != 3 or
        proc.get("fourth_wait_completed") is not True or
        proc.get("fifth_wait_completed") is not True or
        proc.get("same_emulator_data_root") is not True):
        raise ValueError("fresh fourth/fifth process not evidenced")
    if {p.name for p in fourth_screens.glob("*.png")} != {
            n+".png" for n in FOURTH}:
        raise ValueError("missing/extra fourth-process screenshots")
    if {p.name for p in fifth_screens.glob("*.png")} != {
            n+".png" for n in FIFTH}:
        raise ValueError("missing/extra fifth-process screenshots")

    a,b=slots(data_root)
    older=a.read_bytes()
    replacement=b.read_bytes()
    if (not valid_slot(older) or not valid_slot(replacement) or
        int.from_bytes(older[4:12],"little") != 1 or
        int.from_bytes(replacement[4:12],"little") != 2 or
        digest(older) != fault["original_slot_a_sha256"] or
        digest(replacement) in {
            fault["original_slot_b_sha256"],
            fault["tampered_slot_b_sha256"]}):
        raise ValueError("journal was not repaired by the fourth guest")

    pixel_counts={
        "fourth_warn":exact_plaque(
            fourth_screens/(FOURTH[0]+".png"),SD_WARN_COLOR,"SD WARN"),
        "fourth_saved":exact_plaque(
            fourth_screens/(FOURTH[1]+".png"),GREEN,"SD SAVED"),
        "fifth_loaded":exact_plaque(
            fifth_screens/(FIFTH[1]+".png"),SD_LOADED_COLOR,"SD LOADED")
    }
    scenes={
        "fourth_post_save":compare_scene(
            reference/(NAMES[0]+".png"),
            fourth_screens/(FOURTH[2]+".png")),
        "fifth_fresh":compare_scene(
            reference/(NAMES[0]+".png"),
            fifth_screens/(FIFTH[0]+".png")),
        "fifth_restored":compare_scene(
            reference/(NAMES[0]+".png"),
            fifth_screens/(FIFTH[2]+".png"))
    }
    ok = (all(v==0 for v in pixel_counts.values()) and
          all(s["exact_visible_rgb_match"] for s in scenes.values()))
    report={
        "kind":"nexium_fourth_guest_repaired_sdmc_fifth_guest_reloaded",
        "journal_a_crc_valid":True,
        "journal_b_crc_valid":True,
        "generation_a":1,
        "generation_b":2,
        "older_generation_unchanged":True,
        "newer_generation_repaired":True,
        "fourth_and_fifth_process_independent":True,
        "status_plaque_mismatches":pixel_counts,
        "scene_exact_visible_rgb":{
            key:val["exact_visible_rgb_match"] for key,val in scenes.items()},
        "scene_pixels_compared":sum(
            x["visible_pixels_compared"] for x in scenes.values()),
        "screenshots_sha256":{
            **{"fourth_"+n:digest((fourth_screens/(n+".png")).read_bytes())
               for n in FOURTH},
            **{"fifth_"+n:digest((fifth_screens/(n+".png")).read_bytes())
               for n in FIFTH}
        },
        "new_journal_b_sha256":digest(replacement),
        "all_checks_passed":ok,
        "physical_sd_or_power_loss_tested":False
    }
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("reference","fourth-screens","fifth-screens",
                 "data-root","damage-manifest","process-manifest","output"):
        parser.add_argument("--"+name,required=True,type=Path)
    v=parser.parse_args()
    try:
        result=audit_repair(v.reference,v.fourth_screens,v.fifth_screens,
                            v.data_root,v.damage_manifest,
                            v.process_manifest,v.output)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        parser.exit(2,"SD repair evidence rejected: "+str(exc)+"\n")
    print(json.dumps({
        "fourth_fifth_repair_confirmed":result["all_checks_passed"],
        "journal_generations":[result["generation_a"],result["generation_b"]],
        "status_plaque_mismatches":result["status_plaque_mismatches"],
        "scene_pixels_compared":result["scene_pixels_compared"]
    },sort_keys=True))
    if not result["all_checks_passed"]:
        parser.exit(1,"NeXium post-repair guest pixel mismatch\n")


if __name__=="__main__":
    main()
