"""ROM-free Stage431 pair comparison, original assets never required."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_surf_paused_vram_pair import (  # noqa: E402
    RAW_VRAM_BYTES, audit_private_surf_capture_pair,
    compare_private_paused_snapshots, read_verified_paused_capture,
)
from capture_private_pcsx_redux_vram import MANIFEST_KIND  # noqa: E402

COLORS = struct.pack("<16H", 0, 0x1f, 0x3e0, 0x7c00, *([0x7fff]*12))
COLORS2 = struct.pack("<16H", 0, 0x11, 0x3d0, 0x7a00, *([0x7700]*12))
BANK = COLORS + COLORS2 + bytes(512 - 64)


def empty_vram():
    return bytearray(RAW_VRAM_BYTES)


def insert_at(raw, x, y, row=COLORS):
    assert x >= 0 and y >= 0
    off = (y*1024 + x)*2
    raw[off:off+32] = row


def compare(a, b, banks=None, **opts):
    if banks is None:
        banks = [BANK]
    return compare_private_paused_snapshots(
        {"bytes": bytes(a)}, {"bytes": bytes(b)}, banks, **opts)


def publish_fake_paused_capture(root, basename, data, *,
                                label="Surf Village", **overrides):
    manifest = {
        "schema": 1, "kind": MANIFEST_KIND,
        "source": "PCSX-Redux localhost GET /api/v1/gpu/vram/raw",
        "vram_filename": basename + ".u16le.bin",
        "manifest_filename": basename + ".capture.json",
        "bytes": RAW_VRAM_BYTES,
        "vram_sha256": hashlib.sha256(data).hexdigest(),
        "snapshot_read_count": 2,
        "execution_flow_read_count": 3,
        "api_reported_running_false_in_all_three_observations": True,
        "two_read_bytes_identical": True,
        "emulator_was_paused_at_capture_unverified": True,
        "game_map_and_frame_number_unverified": True,
        "not_evidence_of_runtime_clut_selection": True,
        "operator_scene_label": label,
    }
    manifest.update(overrides)
    root = Path(root)
    (root / (basename + ".u16le.bin")).write_bytes(data)
    (root / (basename + ".capture.json")).write_text(json.dumps(manifest),
                                                       encoding="utf-8")


class Stage431VRAMPairTests(unittest.TestCase):
    def test_exact_common_palette_coordinate_and_single_word_delta(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a, 16, 14)
        insert_at(b, 16, 14)
        b[12000] = 8
        result = compare(a, b)
        row = next(x for x in result["candidate_rows"]
                   if x["candidate_row_sha256"] ==
                      hashlib.sha256(COLORS).hexdigest())
        self.assertEqual(row["classification"], "COMMON_COORDINATES")
        self.assertEqual(row["common_coordinate_count"], 1)
        self.assertEqual(row["common_coordinate_samples"],
                         [{"x_words": 16, "y": 14}])
        self.assertEqual(result["changed_u16_word_count"], 1)
        self.assertEqual(result["changed_16word_grid_cell_count"], 1)
        self.assertFalse(result["snapshots_byte_identical"])

    def test_distinct_palette_rows_stay_independent(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a, 32, 17, COLORS)
        insert_at(b, 64, 17, COLORS2)
        result = compare(a, b)
        classes = {r["candidate_row_sha256"]: r["classification"]
                   for r in result["candidate_rows"]}
        self.assertEqual(classes[hashlib.sha256(COLORS).hexdigest()], "FIRST_ONLY")
        self.assertEqual(classes[hashlib.sha256(COLORS2).hexdigest()], "SECOND_ONLY")

    def test_present_in_both_but_different_clut_coordinates(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a, 16, 17)
        insert_at(b, 32, 17)
        rows = compare(a,b)["candidate_rows"]
        matched = [x for x in rows if x["classification"] ==
                   "BOTH_PRESENT_DIFFERENT_COORDINATES"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["common_coordinate_count"], 0)

    def test_both_absent(self):
        result = compare(empty_vram(), empty_vram())
        self.assertEqual(result["row_classes"]["ABSENT_BOTH"], 2)
        self.assertEqual(result["changed_u16_word_count"], 0)
        self.assertTrue(result["snapshots_byte_identical"])

    def test_duplicated_candidate_palettes_preserve_both_references(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a, 0, 0)
        insert_at(b, 0, 0)
        result = compare(a, b, banks=[BANK, BANK])
        row = next(r for r in result["candidate_rows"] if
                   r["candidate_row_sha256"] == hashlib.sha256(COLORS).hexdigest())
        self.assertEqual(row["common_coordinate_count"], 1)
        self.assertEqual(row["candidate_bank_row_references"], [
            {"candidate_bank_index": 0,"candidate_row_index": 0},
            {"candidate_bank_index": 1,"candidate_row_index": 0}])
        self.assertEqual(result["candidate_bank_count"], 2)
        self.assertEqual(result["eligible_distinct_candidate_row_count"], 2)

    def test_x1008_and_y511_last_valid_clut_grid_cell(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a,1008,511)
        insert_at(b,1008,511)
        result=compare(a,b)
        row = next(r for r in result["candidate_rows"] if
                   r["candidate_row_sha256"] == hashlib.sha256(COLORS).hexdigest())
        self.assertEqual(row["common_coordinate_samples"],
                         [{"x_words":1008,"y":511}])

    def test_unaligned_false_positive_not_reported(self):
        a, b = empty_vram(), empty_vram()
        insert_at(a,17,8)
        insert_at(b,17,8)
        result = compare(a,b)
        self.assertEqual(result["row_classes"]["ABSENT_BOTH"],2)

    def test_low_information_palette_rows_excluded(self):
        result = compare(empty_vram(), empty_vram(), banks=[BANK])
        self.assertEqual(result["excluded_all_zero_rows"],14)
        self.assertEqual(result["excluded_low_distinct_nonzero_rows"],0)
        self.assertEqual(result["eligible_distinct_candidate_row_count"],2)
        with self.assertRaises(ValueError):
            compare(empty_vram(),empty_vram(),minimum_distinct_nonzero=0)

    def test_sample_cap_not_total_count(self):
        a,b=empty_vram(),empty_vram()
        for x in (16,32,48,64):
            insert_at(a,x,31)
            insert_at(b,x,31)
        row=next(r for r in compare(a,b,max_position_samples=2)["candidate_rows"]
                 if r["candidate_row_sha256"] == hashlib.sha256(COLORS).hexdigest())
        self.assertEqual(row["common_coordinate_count"],4)
        self.assertEqual(len(row["common_coordinate_samples"]),2)
        self.assertTrue(row["common_coordinate_samples_truncated"])

    def test_integrity_valid_capture_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            raw=bytes(empty_vram())
            publish_fake_paused_capture(td,"one",raw)
            checked=read_verified_paused_capture(td,"one")
            self.assertEqual(checked["bytes"],raw)
            self.assertEqual(checked["sha256"],hashlib.sha256(raw).hexdigest())

    def test_corrupted_vram_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            raw=bytes(empty_vram())
            publish_fake_paused_capture(td,"one",raw)
            dest=Path(td)/"one.u16le.bin"
            with dest.open("r+b") as f:
                f.seek(99)
                f.write(b"z")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                read_verified_paused_capture(td,"one")

    def test_stage429_single_capture_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            publish_fake_paused_capture(td,"one",bytes(empty_vram()),
                                        snapshot_read_count=1)
            with self.assertRaisesRegex(ValueError,"Stage430"):
                read_verified_paused_capture(td,"one")

    def test_nonbool_pause_proof_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            publish_fake_paused_capture(td,"one",bytes(empty_vram()),
                api_reported_running_false_in_all_three_observations=1)
            with self.assertRaisesRegex(ValueError,"Stage430"):
                read_verified_paused_capture(td,"one")

    def test_duplicate_manifest_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            publish_fake_paused_capture(td,"one",bytes(empty_vram()))
            manifest=Path(td)/"one.capture.json"
            text=manifest.read_text()
            manifest.write_text(text[:-1]+',"schema":1}')
            with self.assertRaisesRegex(ValueError,"duplicate"):
                read_verified_paused_capture(td,"one")

    def test_missing_or_wrong_length_capture_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            publish_fake_paused_capture(td,"one",bytes(empty_vram())[:-1])
            with self.assertRaisesRegex(ValueError,"length invalid"):
                read_verified_paused_capture(td,"one")

    def test_symlink_capture_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            publish_fake_paused_capture(folder,"one",bytes(empty_vram()))
            (folder/"two.capture.json").symlink_to(folder/"one.capture.json")
            with self.assertRaisesRegex(ValueError,"symlink"):
                read_verified_paused_capture(folder,"two")

    def test_manifest_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            publish_fake_paused_capture(td,"one",bytes(empty_vram()),
                                        vram_filename="../private.bin")
            with self.assertRaisesRegex(ValueError,"Stage430"):
                read_verified_paused_capture(td,"one")

    def test_pair_end_to_end_synthetic_private_reader(self):
        with tempfile.TemporaryDirectory() as td:
            a,b=empty_vram(),empty_vram()
            insert_at(a,64,19)
            insert_at(b,64,19)
            publish_fake_paused_capture(td,"first",bytes(a))
            publish_fake_paused_capture(td,"second",bytes(b))
            with patch("audit_surf_paused_vram_pair.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[{"graphics_region_index":6}]}):
                report=audit_private_surf_capture_pair(
                    "/never/real/assets.bin",td,"first","second")
            self.assertEqual(report["map_index"],2)
            self.assertEqual(report["bounded_lzss_stream_count"],1)
            self.assertEqual(report["row_classes"]["COMMON_COORDINATES"],1)
            self.assertTrue(report["capture_labels_same_but_not_authenticated"])

    def test_pair_different_labels_rejected_without_private_source_read(self):
        with tempfile.TemporaryDirectory() as td:
            raw=bytes(empty_vram())
            publish_fake_paused_capture(td,"first",raw,label="Surf Village")
            publish_fake_paused_capture(td,"second",raw,label="Different Scene")
            with patch("audit_surf_paused_vram_pair.read_private_candidates") as fetch:
                with self.assertRaisesRegex(ValueError,"labels differ"):
                    audit_private_surf_capture_pair("unused",td,"first","second")
                fetch.assert_not_called()

    def test_pair_same_basename_rejected(self):
        with self.assertRaisesRegex(ValueError,"distinct capture basenames"):
            audit_private_surf_capture_pair("unused","unused","first","first")

    def test_privacy_no_raw_palette_or_pixels_in_metadata(self):
        a,b=empty_vram(),empty_vram()
        insert_at(a,32,20)
        insert_at(b,32,20)
        report=compare(a,b)
        encoded=json.dumps(report)
        for forbidden in ('"raw_vram"','"raw_palette"','"palette_words"',
                          '"decoded_pixels"','"game_screenshot"'):
            self.assertNotIn(forbidden,encoded)
        self.assertTrue(report["interpretation"][
            "common_grid_coordinate_not_proof_of_gpu_clut_use"])
        self.assertTrue(report["interpretation"][
            "no_original_color_words_or_pixels_exported"])


if __name__ == "__main__":
    unittest.main()
