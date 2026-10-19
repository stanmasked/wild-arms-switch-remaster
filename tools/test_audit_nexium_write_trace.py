#!/usr/bin/env python3
import tempfile
from pathlib import Path
import unittest

from audit_nexium_write_trace import extract

class TraceExtractionTests(unittest.TestCase):
    def test_failed_readback_preserves_detailed_stage(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"fourth-internal.log"
            file.write_text(
                "2026 DEBUG OutputDebugString: WA_SAVE_TRACE v1 "
                "result=6 ready=1 step=12 oldA=1 oldB=3 "
                "tmp=1 pub=2 gen=2 tries=3 renamed=1 equal=0 errno=0\n")
            report=extract([file])
            self.assertTrue(report["found"])
            r=report["records"][0]
            self.assertEqual(r["step_label"],"failed_readback")
            self.assertEqual(r["attempts"],3)
            self.assertTrue(r["renamed"])
            self.assertFalse(r["bytes_equal"])
            self.assertEqual(r["source"],"fourth-internal.log")
            self.assertEqual(r["result_label"],"io_error")
            self.assertEqual(r["existing_b_label"],"corrupt")
            self.assertEqual(r["failure_class"],
                             "published_record_not_verified")
            self.assertTrue(report["all_fields_valid"])

    def test_success_and_missing_trace(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"fourth-process.log"
            file.write_text(
                "OutputDebugString: WA_SAVE_TRACE v1 "
                "result=0 ready=1 step=8 oldA=1 oldB=3 "
                "tmp=1 pub=1 gen=2 tries=1 renamed=1 equal=1 errno=0\n")
            a=extract([file,Path(td)/"missing.log"])
            self.assertEqual(a["records"][0]["step_label"],
                             "verified_committed")
            self.assertEqual(a["records"][0]["failure_class"],
                             "exact_new_generation_verified")
            self.assertFalse(extract([Path(td)/"missing.log"])["found"])
            self.assertFalse(extract([Path(td)/"missing.log"])["all_fields_valid"])

    def test_distinct_failures_not_misclassified_as_verified(self):
        scenarios = (
            (1, "preexisting_slot_read_error"),
            (2, "temporary_file_open_error"),
            (9, "temporary_write_sync_or_close_failed"),
            (10, "temporary_record_verification_failed"),
            (11, "old_slot_unlink_failed"),
            (12, "published_record_not_verified"),
        )
        for step, reason in scenarios:
            with self.subTest(stage=step):
                with tempfile.TemporaryDirectory() as td:
                    file=Path(td)/"fourth-internal.log"
                    file.write_text(
                        "OutputDebugString: WA_SAVE_TRACE v1 "
                        f"result=6 ready=1 step={step} oldA=1 oldB=3 "
                        "tmp=1 pub=2 gen=2 tries=3 renamed=1 "
                        "equal=0 errno=5\n")
                    report=extract([file])
                    self.assertEqual(report["failure_classes"],[reason])
                    self.assertTrue(report["all_fields_valid"])

    def test_missing_guest_trace_cannot_assert_phase(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"host.log"
            file.write_text("no OutputDebugString lines\n")
            audit=extract([file])
            self.assertFalse(audit["found"])
            self.assertEqual(audit["failure_classes"],[])
            self.assertFalse(audit["all_fields_valid"])

    def test_invalid_trace_flags_are_not_interpreted(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"fourth.log"
            file.write_text(
                "OutputDebugString: WA_SAVE_TRACE v1 "
                "result=0 ready=1 step=8 oldA=1 oldB=3 "
                "tmp=1 pub=1 gen=2 tries=1 renamed=9 equal=1 errno=0\n")
            audit=extract([file])
            self.assertTrue(audit["found"])
            self.assertFalse(audit["all_fields_valid"])
            self.assertEqual(audit["failure_classes"],
                             ["malformed_trace_fields"])

    def test_isolated_guest_sdmc_diagnostic_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"fourth-save-phase.txt"
            file.write_text(
                "WA_SAVE_TRACE v1 result=6 ready=1 step=9 "
                "oldA=1 oldB=3 tmp=2 pub=2 gen=2 "
                "tries=0 renamed=0 equal=0 errno=5\n")
            report=extract([file])
            self.assertTrue(report["found"])
            self.assertTrue(report["all_fields_valid"])
            self.assertEqual(report["failure_classes"],
                             ["temporary_write_sync_or_close_failed"])
            self.assertEqual(report["records"][0]["source"],
                             "fourth-save-phase.txt")

    def test_readback_evidence_disambiguates_corrupt_reason(self):
        cases = (
            ("count=9 eof=1 more=0 magic=0 crc=0 decoded=0",
             "readback_short_record"),
            ("count=56 eof=0 more=1 magic=0 crc=0 decoded=0",
             "readback_extra_byte"),
            ("count=56 eof=1 more=0 magic=0 crc=1 decoded=0",
             "readback_header_mismatch"),
            ("count=56 eof=1 more=0 magic=1 crc=0 decoded=0",
             "readback_crc_mismatch"),
            ("count=56 eof=1 more=0 magic=1 crc=1 decoded=0",
             "readback_decode_rejected"),
            ("count=56 eof=1 more=0 magic=1 crc=1 decoded=1",
             "readback_payload_differs"),
        )
        for fields, label in cases:
            with self.subTest(readback=label):
                with tempfile.TemporaryDirectory() as td:
                    path=Path(td)/"fourth-save-phase.txt"
                    path.write_text(
                        "WA_SAVE_TRACE v1 result=6 ready=1 step=12 "
                        "oldA=1 oldB=3 tmp=1 pub=3 gen=2 "
                        "tries=3 renamed=1 equal=0 errno=0 "
                        + fields + "\n")
                    report=extract([path])
                    self.assertTrue(report["all_fields_valid"])
                    self.assertTrue(report["records"][0]["extended_readback"])
                    self.assertEqual(report["failure_classes"],[label])

    def test_rescue_success_requires_full_verified_publication(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"guest.txt"
            path.write_text(
                "WA_SAVE_TRACE v1 result=0 ready=1 step=14 "
                "oldA=1 oldB=3 tmp=1 pub=1 gen=2 "
                "tries=4 renamed=1 equal=1 errno=0 "
                "count=56 eof=1 more=0 magic=1 crc=1 decoded=1\n")
            a=extract([path])
            self.assertTrue(a["all_fields_valid"])
            self.assertEqual(a["failure_classes"],
                             ["exact_new_generation_rescued"])
            path.write_text(path.read_text().replace("equal=1", "equal=0"))
            bad=extract([path])
            self.assertEqual(bad["failure_classes"],
                             ["reported_success_missing_proof"])

    def test_rescue_failure_cannot_be_mistaken_for_success(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"guest.txt"
            path.write_text(
                "WA_SAVE_TRACE v1 result=6 ready=1 step=15 "
                "oldA=1 oldB=3 tmp=1 pub=3 gen=2 "
                "tries=4 renamed=1 equal=0 errno=0 "
                "count=56 eof=1 more=0 magic=1 crc=0 decoded=0\n")
            a=extract([path])
            self.assertEqual(a["failure_classes"],
                             ["redundant_slot_rescue_failed"])

    def test_wrong_marker_does_not_create_false_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"host.log"
            file.write_text(
                "WA_SAVE_TRACE v2 result=0 ready=1 step=8 "
                "oldA=1 oldB=1 tmp=1 pub=1 gen=2 "
                "tries=1 renamed=1 equal=1 errno=0\n")
            self.assertFalse(extract([file])["found"])

if __name__=="__main__":
    unittest.main()
