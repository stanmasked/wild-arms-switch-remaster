"""Synthetic-only cross-check of raw PS1 ISO extent and private CDSTG parser."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_private_cdstg_disc_source import (  # noqa: E402
    _file_sha256, _trusted_structural_summary, audit_private_cdstg_disc_source,
)
from extract_private_cdstg_from_cue_bin import RAW_SECTOR  # noqa: E402
from test_extract_private_cdstg_from_cue_bin import (  # noqa: E402
    BYTES, SECTORS, cue, synthetic_disc,
)

SYNTHETIC_STRUCTURAL = {
    "map_index": 2,
    "candidate_512_byte_bank_count": 1,
    "verified_bounded_lzss_stream_count": 1,
    "candidate_16_color_row_count": 16,
    "byte_distinct_palette_row_count": 4,
    "all_zero_candidate_row_count": 2,
}


def fixtures(directory):
    root = Path(directory)
    binary = root / "synthetic.bin"
    synthetic_disc(binary, file_data=BYTES)
    descriptor = root / "synthetic.cue"
    cue(descriptor)
    extracted = root / "CDSTG.BIN"
    extracted.write_bytes(BYTES)
    return descriptor, binary, extracted


def audit(cue_path, extracted_path, **options):
    return audit_private_cdstg_disc_source(
        cue_path, extracted_path, expected_extracted_bytes=len(BYTES),
        expected_banks=1, expected_streams=1, **options)


class Stage436CrossSourceTests(unittest.TestCase):
    def test_synthetic_disc_and_private_file_exact_match(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, binary, extracted = fixtures(td)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       return_value=dict(SYNTHETIC_STRUCTURAL)) as decoder:
                result = audit(descriptor, extracted, expected_raw_sector_count=SECTORS)
                decoder.assert_called_once_with(extracted, map_index=2)
            self.assertEqual(result["source_cd_resource_sha256"],
                             hashlib.sha256(BYTES).hexdigest())
            self.assertEqual(result["private_extraction_sha256"],
                             result["source_cd_resource_sha256"])
            self.assertEqual(result["cdstg_iso_extent_start_lba"], 18)
            self.assertTrue(result["source_and_extracted_bytes_identical"])
            self.assertEqual(result["candidate_16_color_row_count"], 16)
            self.assertEqual(result["raw_sector_bytes"], RAW_SECTOR)
            self.assertTrue(result["interpretation"][
                "palette_row_to_texture_assignment_unverified"])

    def test_byte_modified_private_extraction_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            raw = bytearray(BYTES)
            raw[3] ^= 1
            extracted.write_bytes(raw)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates") as decoder:
                with self.assertRaisesRegex(ValueError, "does not byte-match"):
                    audit(descriptor, extracted)
                decoder.assert_not_called()

    def test_byte_modified_source_disc_extent_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, binary, extracted = fixtures(td)
            with binary.open("r+b") as stream:
                stream.seek(18*RAW_SECTOR + 24 + 4)
                stream.write(b"Q")
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates") as decoder:
                with self.assertRaisesRegex(ValueError, "does not byte-match"):
                    audit(descriptor, extracted)
                decoder.assert_not_called()

    def test_mismatched_raw_disc_sector_count_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates") as decoder:
                with self.assertRaisesRegex(ValueError, "sector count"):
                    audit(descriptor, extracted,
                          expected_raw_sector_count=SECTORS+1)
                decoder.assert_not_called()

    def test_wrong_extracted_byte_length_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            extracted.write_bytes(BYTES[:-1])
            with self.assertRaisesRegex(ValueError, "geometry"):
                audit(descriptor, extracted)

    def test_structural_banks_not_matching_expectation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            incorrect = dict(SYNTHETIC_STRUCTURAL)
            incorrect["candidate_512_byte_bank_count"] = 2
            incorrect["candidate_16_color_row_count"] = 32
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       return_value=incorrect):
                with self.assertRaisesRegex(ValueError, "structure differs"):
                    audit(descriptor, extracted)

    def test_structural_streams_not_matching_expectation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            incorrect = dict(SYNTHETIC_STRUCTURAL)
            incorrect["verified_bounded_lzss_stream_count"] = 2
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       return_value=incorrect):
                with self.assertRaisesRegex(ValueError, "structure differs"):
                    audit(descriptor, extracted)

    def test_structural_summary_rejects_ill_formed_response(self):
        for result in (
            {}, {"map_index": 2},
            {**SYNTHETIC_STRUCTURAL, "map_index": True},
            {**SYNTHETIC_STRUCTURAL, "map_index": 3},
            {**SYNTHETIC_STRUCTURAL, "candidate_16_color_row_count": 15},
            {**SYNTHETIC_STRUCTURAL, "candidate_512_byte_bank_count": True},
            {**SYNTHETIC_STRUCTURAL, "byte_distinct_palette_row_count": 20},
            {**SYNTHETIC_STRUCTURAL, "all_zero_candidate_row_count": -1},
        ):
            with self.subTest(report=result), self.assertRaises(ValueError):
                _trusted_structural_summary(result, 2)

    def test_detects_bin_changed_during_structure_check(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, binary, extracted = fixtures(td)
            def mutate_source(*args, **kwargs):
                with binary.open("r+b") as file:
                    file.seek(18*RAW_SECTOR + 24)
                    file.write(b"M")
                return dict(SYNTHETIC_STRUCTURAL)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       side_effect=mutate_source):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    audit(descriptor, extracted)

    def test_detects_extraction_changed_during_structure_check(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            def mutate_extraction(*args, **kwargs):
                with extracted.open("r+b") as stream:
                    stream.seek(0)
                    stream.write(b"R")
                return dict(SYNTHETIC_STRUCTURAL)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       side_effect=mutate_extraction):
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    audit(descriptor, extracted)

    def test_rejects_symlinked_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            link = Path(td)/"symlink.BIN"
            link.symlink_to(extracted)
            with self.assertRaisesRegex(ValueError, "regular private file"):
                audit(descriptor, link)

    def test_rejects_invalid_audit_bounds_before_disc_read(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            for options in ({"map_index": True},
                            {"map_index": 128},
                            {"expected_extracted_bytes": False},
                            {"expected_raw_sector_count": 1},
                            {"expected_raw_sector_count": True},
                            {"expected_banks": 0},
                            {"expected_streams": 65}):
                with self.subTest(opts=options),self.assertRaises(ValueError):
                    audit(descriptor, extracted, **options)

    def test_truncated_map_is_not_accepted_if_sha_valid(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       side_effect=ValueError("invalid increasing graphics pointer run")):
                with self.assertRaisesRegex(ValueError, "graphics pointer"):
                    audit(descriptor, extracted)

    def test_wrong_original_cue_file_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            descriptor.write_text('FILE "../unsafe.bin" BINARY\n'
                                  '  TRACK 01 MODE2/2352\n'
                                  '    INDEX 01 00:00:00\n')
            with self.assertRaisesRegex(ValueError, "one MODE2"):
                audit(descriptor, extracted)

    def test_private_hash_manifest_no_source_bytes_or_palette_words(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, _, extracted = fixtures(td)
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       return_value=dict(SYNTHETIC_STRUCTURAL)):
                result = audit(descriptor, extracted)
            report=json.dumps(result)
            self.assertNotIn(BYTES.decode("ascii"),report)
            for unwanted in ('"decoded_sprites"','"original_ps1_pixels"',
                             '"raw_palette_u16"','"raw_cd_sector_bytes"'):
                self.assertNotIn(unwanted,report)
            self.assertTrue(result["interpretation"]["metadata_and_hashes_also_private"])

    def test_no_new_files_written_by_audit(self):
        with tempfile.TemporaryDirectory() as td:
            descriptor, binary, extracted=fixtures(td)
            before = sorted(p.name for p in Path(td).iterdir())
            with patch("audit_private_cdstg_disc_source.audit_palette_candidates",
                       return_value=dict(SYNTHETIC_STRUCTURAL)):
                audit(descriptor, extracted)
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()),before)

    def test_file_digest_detects_wrong_length(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/"file.bin"
            output.write_bytes(BYTES)
            self.assertEqual(_file_sha256(output,len(BYTES)),
                             hashlib.sha256(BYTES).hexdigest())
            with self.assertRaisesRegex(ValueError, "geometry"):
                _file_sha256(output,len(BYTES)+1)


if __name__ == "__main__":
    unittest.main()
