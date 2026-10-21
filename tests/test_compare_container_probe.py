"""Synthetic-only tests for comparison with the prior private probe schema."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_container_probe import compare  # noqa: E402


class CompareContainerProbeTests(unittest.TestCase):
    def _write_json(self, folder, name, value):
        path = Path(folder) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _reference(self):
        return {
            "kind": "PRIVATE_DISC_HEADER_PROBE",
            "probed_files": [{
                "path": "BIN/CDSTG.BIN;1",
                "file_size_bytes": 1024,
                "header_sample_length": 8,
                "header_sample_sha256": "abc123",
            }],
        }

    def _actual(self, mode="prefix", size=1024, sample_length=8, sample_hash="abc123", name="CDSTG.BIN"):
        return {
            "kind": "BOUNDED_LOCAL_CONTAINER_PROBE",
            "input_name": name,
            "file_size_bytes": size,
            "sample": {"mode": mode, "bytes_read": sample_length, "sha256": sample_hash},
        }

    def test_matches_reference_case_insensitive_and_strips_iso_version(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = self._write_json(folder, "reference.json", self._reference())
            actual = self._write_json(folder, "actual.json", self._actual(name="cdstg.bin"))
            result = compare(reference, [actual])
        self.assertEqual(result["overall"], "PASS")
        self.assertEqual(result["comparisons"][0]["file"], "CDSTG.BIN")
        self.assertEqual(result["comparisons"][0]["status"], "MATCH")

    def test_reports_all_mismatch_reasons(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = self._write_json(folder, "reference.json", self._reference())
            actual = self._write_json(
                folder, "actual.json",
                self._actual(mode="distributed", size=999, sample_length=4, sample_hash="wrong"),
            )
            result = compare(reference, [actual])
        self.assertEqual(result["overall"], "FAIL")
        self.assertEqual(
            result["comparisons"][0]["reasons"],
            ["FILE_SIZE_MISMATCH", "SAMPLE_MODE_NOT_PREFIX", "SAMPLE_LENGTH_MISMATCH", "PREFIX_SHA256_MISMATCH"],
        )

    def test_unknown_file_is_explicit_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = self._write_json(folder, "reference.json", self._reference())
            actual = self._write_json(folder, "actual.json", self._actual(name="UNKNOWN.BIN"))
            result = compare(reference, [actual])
        self.assertEqual(result["overall"], "FAIL")
        self.assertEqual(result["comparisons"][0]["reasons"], ["NO_REFERENCE_ENTRY"])

    def test_rejects_wrong_reference_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = self._write_json(folder, "reference.json", {"kind": "wrong"})
            actual = self._write_json(folder, "actual.json", self._actual())
            with self.assertRaisesRegex(ValueError, "PRIVATE_DISC_HEADER_PROBE"):
                compare(reference, [actual])

    def test_rejects_duplicate_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            reference = self._write_json(folder, "reference.json", self._reference())
            actual = self._write_json(folder, "actual.json", self._actual())
            with self.assertRaisesRegex(ValueError, "duplicate"):
                compare(reference, [actual, actual])


if __name__ == "__main__":
    unittest.main()
