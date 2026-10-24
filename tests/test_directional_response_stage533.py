"""Synthetic-only tests for the Stage533 aggregate directional-report gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_directional_response_stage533 import validate, load_report

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def report():
    metrics = []
    shifts = {"none": (0.06, 0.04, 0.75), "left": (56.0, 0.0, 0.52),
              "right": (-27.0, 0.0, 0.63), "up": (0.0, 36.0, 0.45),
              "down": (0.0, -58.0, 0.40)}
    after_hashes = {"none": SHA_B, "left": SHA_C, "right": "d"*64,
                    "up": "e"*64, "down": "f"*64}
    for direction, (x, y, response) in shifts.items():
        after_hash = after_hashes[direction]
        metrics.append({
            "direction": direction,
            "input_override_frames": 0 if direction == "none" else 30,
            "initial_vram_sha256": SHA_A,
            "after_vram_sha256": after_hash,
            "repeat_initial_vram_sha256": SHA_A,
            "repeat_after_vram_sha256": after_hash,
            "initial_vram_exact_repeat_match": True,
            "after_vram_exact_repeat_match": True,
            "before_after_changed_grayscale_pixels": 0 if direction == "none" else 50000,
            "mean_absolute_grayscale_difference": 0.5 if direction == "none" else 20.0,
            "background_phase_correlation_shift_px": {"x": x, "y": y, "response": response},
            "blue_dominant_component_before": None,
            "blue_dominant_component_after": None,
            "saved_state_bytes_equal_across_repeats": False,
        })
    return {
        "checkpoint_sha256": SHA_C,
        "direction_signs_match_expected_opposite_background_motion": True,
        "exact_vram_repeat_match_all_directions": True,
        "initial_vram_common_sha256": SHA_A,
        "kind": "WA1_STAGE533_FOUR_WAY_DIRECTIONAL_RESPONSE",
        "limits": {
            "gui_capture_origin_cryptographically_attested": False,
            "internal_field_map_index_confirmed": False,
            "physical_controller_input_attested": False,
            "ps1_hardware_parity_confirmed": False,
            "switch_runtime_or_hardware_parity_confirmed": False,
        },
        "metrics": metrics,
        "neutral_control_within_one_pixel": True,
        "prior_stage532_drive_readback": {
            "byte_exact_match": True, "file_ref": "https://drive.google.com/file/d/synthetic",
            "member_hashes": "PASS", "sha256": SHA_B, "zip_crc": "PASS",
        },
        "runtime": {"pcsx_redux_commit": "synthetic", "appimage_sha256": SHA_C,
                    "appimage_drive_ref": "https://drive.google.com/file/d/synthetic",
                    "bios": "OpenBIOS", "cpu": "dynarec", "renderer": "software GPU",
                    "source_checkpoint": "synthetic.state"},
        "same_initial_vram_across_all_directions": True,
        "schema": 1,
        "source_disc": {"bin_drive_ref": "https://drive.google.com/file/d/synthetic",
                        "bin_name": "synthetic.bin", "bin_sha256": SHA_A, "bin_size": 4704,
                        "canonical_bin_cue_not_bundled": True,
                        "cue_drive_ref": "https://drive.google.com/file/d/synthetic",
                        "cue_name": "synthetic.cue", "cue_sha256": SHA_B, "cue_size": 81,
                        "track_mode": "MODE2/2352"},
        "state_serialization_note": "Synthetic note: state bytes differ despite identical VRAM output.",
        "status": "PASS_DIRECTIONAL_RESPONSE_AND_VRAM_REPEATABILITY_SOFTWARE_GPU_ONLY",
    }


class Stage533DirectionalReportTests(unittest.TestCase):
    def test_valid_synthetic_report(self):
        self.assertTrue(validate(report()))

    def test_wrong_direction_sign_rejected(self):
        data = report()
        next(x for x in data["metrics"] if x["direction"] == "left")["background_phase_correlation_shift_px"]["x"] = -56.0
        with self.assertRaisesRegex(ValueError, "directional displacement"):
            validate(data)

    def test_neutral_motion_over_one_pixel_rejected(self):
        data = report()
        next(x for x in data["metrics"] if x["direction"] == "none")["background_phase_correlation_shift_px"]["x"] = 1.01
        with self.assertRaisesRegex(ValueError, "neutral control"):
            validate(data)

    def test_initial_vram_mismatch_rejected(self):
        data = report()
        next(x for x in data["metrics"] if x["direction"] == "up")["initial_vram_sha256"] = SHA_B
        with self.assertRaisesRegex(ValueError, "initial VRAM checkpoint differs"):
            validate(data)

    def test_repeat_output_hash_mismatch_rejected(self):
        data = report()
        next(x for x in data["metrics"] if x["direction"] == "down")["repeat_after_vram_sha256"] = SHA_A
        with self.assertRaisesRegex(ValueError, "repeat after-VRAM hash mismatch"):
            validate(data)

    def test_repeat_claim_without_exact_flags_rejected(self):
        data = report()
        next(x for x in data["metrics"] if x["direction"] == "right")["after_vram_exact_repeat_match"] = False
        with self.assertRaisesRegex(ValueError, "repeat VRAM mismatch"):
            validate(data)

    def test_unverified_switch_claim_rejected(self):
        data = report()
        data["limits"]["switch_runtime_or_hardware_parity_confirmed"] = True
        with self.assertRaisesRegex(ValueError, "must remain explicitly false"):
            validate(data)

    def test_missing_direction_rejected(self):
        data = report()
        data["metrics"] = [x for x in data["metrics"] if x["direction"] != "up"]
        with self.assertRaisesRegex(ValueError, "exactly five"):
            validate(data)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text('{"schema":1,"schema":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_report(path)

    def test_nonfinite_json_number_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            path.write_text('{"value":NaN}')
            with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
                load_report(path)


if __name__ == "__main__":
    unittest.main()
