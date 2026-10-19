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
            self.assertFalse(extract([Path(td)/"missing.log"])["found"])

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
