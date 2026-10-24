#!/usr/bin/env python3
"""Validate Stage533 directional-response aggregate metadata, not raw evidence.

This gate checks the structure and internal consistency of a private analysis
summary. It does not attest gameplay, validate screenshots, or recompute image
correlation from the raw VRAM files. Use the private evidence bundle for that.
"""
import argparse
import json
import math
from pathlib import Path
import re
import stat

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DIRECTIONS = ("none", "left", "right", "up", "down")
TOP_KEYS = {
    "checkpoint_sha256", "direction_signs_match_expected_opposite_background_motion",
    "exact_vram_repeat_match_all_directions", "initial_vram_common_sha256", "kind",
    "limits", "metrics", "neutral_control_within_one_pixel", "prior_stage532_drive_readback",
    "runtime", "same_initial_vram_across_all_directions", "schema", "source_disc",
    "state_serialization_note", "status",
}
METRIC_KEYS = {
    "direction", "input_override_frames", "initial_vram_sha256", "after_vram_sha256",
    "repeat_initial_vram_sha256", "repeat_after_vram_sha256", "initial_vram_exact_repeat_match",
    "after_vram_exact_repeat_match", "before_after_changed_grayscale_pixels",
    "mean_absolute_grayscale_difference", "background_phase_correlation_shift_px",
    "blue_dominant_component_before", "blue_dominant_component_after",
    "saved_state_bytes_equal_across_repeats",
}
LIMIT_KEYS = {
    "gui_capture_origin_cryptographically_attested", "internal_field_map_index_confirmed",
    "physical_controller_input_attested", "ps1_hardware_parity_confirmed",
    "switch_runtime_or_hardware_parity_confirmed",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_report(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 1024 * 1024:
        raise ValueError("report must be a bounded regular single-link file")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def require_sha(value, label):
    if type(value) is not str or not SHA256.fullmatch(value):
        raise ValueError("invalid SHA-256 field: " + label)


def finite_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("invalid numeric field: " + label)
    return float(value)


def validate(data):
    if type(data) is not dict or set(data) != TOP_KEYS:
        raise ValueError("unexpected directional report schema")
    if type(data["schema"]) is not int or data["schema"] != 1 or data["kind"] != "WA1_STAGE533_FOUR_WAY_DIRECTIONAL_RESPONSE":
        raise ValueError("unsupported directional report version")
    if data["status"] != "PASS_DIRECTIONAL_RESPONSE_AND_VRAM_REPEATABILITY_SOFTWARE_GPU_ONLY":
        raise ValueError("unexpected directional report status")
    for field in ("checkpoint_sha256", "initial_vram_common_sha256"):
        require_sha(data[field], field)
    for field in ("same_initial_vram_across_all_directions", "exact_vram_repeat_match_all_directions",
                  "direction_signs_match_expected_opposite_background_motion", "neutral_control_within_one_pixel"):
        if data[field] is not True:
            raise ValueError("required directional gate is not satisfied: " + field)
    if type(data["metrics"]) is not list or len(data["metrics"]) != len(DIRECTIONS):
        raise ValueError("exactly five direction records required")
    metrics = {}
    for record in data["metrics"]:
        if type(record) is not dict or set(record) != METRIC_KEYS:
            raise ValueError("unexpected directional metric fields")
        direction = record["direction"]
        if direction not in DIRECTIONS or direction in metrics:
            raise ValueError("missing, unknown, or duplicate direction")
        metrics[direction] = record
        expected_frames = 0 if direction == "none" else 30
        if type(record["input_override_frames"]) is not int or record["input_override_frames"] != expected_frames:
            raise ValueError("unexpected input duration for " + direction)
        for field in ("initial_vram_sha256", "repeat_initial_vram_sha256", "after_vram_sha256", "repeat_after_vram_sha256"):
            require_sha(record[field], direction + "." + field)
        if record["initial_vram_sha256"] != data["initial_vram_common_sha256"] or record["repeat_initial_vram_sha256"] != data["initial_vram_common_sha256"]:
            raise ValueError("initial VRAM checkpoint differs for " + direction)
        if record["initial_vram_exact_repeat_match"] is not True or record["after_vram_exact_repeat_match"] is not True:
            raise ValueError("repeat VRAM mismatch for " + direction)
        if record["after_vram_sha256"] != record["repeat_after_vram_sha256"]:
            raise ValueError("repeat after-VRAM hash mismatch for " + direction)
        if type(record["before_after_changed_grayscale_pixels"]) is not int or record["before_after_changed_grayscale_pixels"] < 0:
            raise ValueError("invalid changed-pixel count for " + direction)
        if finite_number(record["mean_absolute_grayscale_difference"], direction + ".mean_absolute_grayscale_difference") < 0:
            raise ValueError("negative pixel difference for " + direction)
        shift = record["background_phase_correlation_shift_px"]
        if type(shift) is not dict or set(shift) != {"x", "y", "response"}:
            raise ValueError("invalid phase-correlation fields for " + direction)
        finite_number(shift["x"], direction + ".shift.x")
        finite_number(shift["y"], direction + ".shift.y")
        response = finite_number(shift["response"], direction + ".shift.response")
        if not 0 < response <= 1:
            raise ValueError("invalid phase-correlation response for " + direction)
        if record["saved_state_bytes_equal_across_repeats"] is not False:
            raise ValueError("unresolved savestate-serialization difference must remain visible")
    if set(metrics) != set(DIRECTIONS):
        raise ValueError("all directions must be present")
    if abs(metrics["none"]["background_phase_correlation_shift_px"]["x"]) >= 1 or abs(metrics["none"]["background_phase_correlation_shift_px"]["y"]) >= 1:
        raise ValueError("neutral control exceeds one-pixel displacement")
    for direction, axis, sign in (("left", "x", 1), ("right", "x", -1), ("up", "y", 1), ("down", "y", -1)):
        value = metrics[direction]["background_phase_correlation_shift_px"][axis]
        if sign * finite_number(value, direction + ".shift." + axis) <= 10:
            raise ValueError("directional displacement sign/magnitude inconsistent: " + direction)
    limits = data["limits"]
    if type(limits) is not dict or set(limits) != LIMIT_KEYS or any(value is not False for value in limits.values()):
        raise ValueError("unverified gameplay/hardware claims must remain explicitly false")
    source = data["source_disc"]
    if type(source) is not dict or source.get("canonical_bin_cue_not_bundled") is not True or source.get("track_mode") != "MODE2/2352":
        raise ValueError("canonical source must remain external and referenced")
    require_sha(source.get("bin_sha256"), "source_disc.bin_sha256")
    require_sha(source.get("cue_sha256"), "source_disc.cue_sha256")
    runtime = data["runtime"]
    if type(runtime) is not dict or runtime.get("renderer") != "software GPU" or runtime.get("bios") != "OpenBIOS":
        raise ValueError("unexpected runtime declaration")
    require_sha(runtime.get("appimage_sha256"), "runtime.appimage_sha256")
    readback = data["prior_stage532_drive_readback"]
    if type(readback) is not dict or readback.get("byte_exact_match") is not True or readback.get("zip_crc") != "PASS" or readback.get("member_hashes") != "PASS":
        raise ValueError("Stage532 private archive readback is not verified")
    require_sha(readback.get("sha256"), "prior_stage532_drive_readback.sha256")
    if type(data["state_serialization_note"]) is not str or len(data["state_serialization_note"]) < 30:
        raise ValueError("unresolved state-serialization limitation must be documented")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="path to summary/directional_metrics.json")
    args = parser.parse_args()
    try:
        validate(load_report(args.report))
    except (ValueError, OSError, json.JSONDecodeError):
        parser.exit(2, "INVALID_DIRECTIONAL_AGGREGATE; RAW_EVIDENCE_NOT_RECHECKED\n")
    print("AGGREGATE_DIRECTIONAL_REPORT_CONSISTENT; RAW_EVIDENCE_NOT_RECHECKED")


if __name__ == "__main__":
    main()
