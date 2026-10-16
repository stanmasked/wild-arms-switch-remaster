"""Privacy-preserving local fixture packaging CLI tests."""
import contextlib
from io import StringIO
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from tools.audit_ps1_capture_pack import main
from tests.test_mips_ps1_capture_pack import dumps, BASE
from tools.mips_ps1_matrix_reference import compare


class CapturePackCLITests(unittest.TestCase):
    def _call(self, *, compare_flag=False, wrong_after=False, already_exists=False,
              source_synthetic=True, malformed=False):
        exe,before_regs,after_regs,before,after=dumps()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=[root/name for name in ('EXE','before.json','after.json',
                                           'before.bin','after.bin','private.json')]
            paths[0].write_bytes(exe)
            paths[1].write_text(json.dumps(before_regs))
            paths[2].write_text('secret-original-state {' if malformed else json.dumps(after_regs))
            paths[3].write_bytes(before)
            paths[4].write_bytes(after if not wrong_after else bytes(len(after)))
            if already_exists:
                paths[5].write_text('EXISTING SECRET',encoding='utf8')
            args=['--exe',str(paths[0]),'--before-registers',str(paths[1]),
                  '--after-registers',str(paths[2]),'--before-ram',str(paths[3]),
                  '--after-ram',str(paths[4]),'--output',str(paths[5]),
                  '--ram-base',hex(BASE)]
            if source_synthetic:args.append('--synthetic')
            if compare_flag:args.append('--compare')
            stdout=StringIO()
            with contextlib.redirect_stdout(stdout):
                rc=main(args)
            result=json.loads(stdout.getvalue())
            exists=paths[5].exists()
            if exists:
                raw=paths[5].read_text(encoding='utf8')
                perms=stat.S_IMODE(paths[5].stat().st_mode)
                fixture=json.loads(raw) if not already_exists else None
            else:
                raw='';perms=None;fixture=None
            return rc,result,raw,perms,fixture,exists

    def test_pack_with_compare_matches_synthetic_9_coefficients(self):
        rc,result,raw,perms,fixture,exists=self._call(compare_flag=True)
        self.assertEqual(rc,0)
        self.assertTrue(exists)
        self.assertTrue(result['numerical_comparison_performed'])
        self.assertTrue(result['matches_supplied_nine_coefficients'])
        self.assertEqual(result['matching_coefficient_count'],9)
        self.assertEqual(fixture['expected_matrix_s16'],[4096]*9)
        self.assertNotIn('4096',str(result))

    def test_package_only_skips_emulator_comparison(self):
        rc,result,raw,perms,fixture,exists=self._call()
        self.assertEqual(rc,0)
        self.assertTrue(exists)
        self.assertFalse(result['numerical_comparison_performed'])
        self.assertNotIn('matching_coefficient_count',result)

    def test_pack_private_file_mode_is_owner_only(self):
        rc,result,raw,perms,fixture,exists=self._call()
        self.assertEqual(rc,0)
        if os.name=='posix':self.assertEqual(perms,0o600)

    def test_compare_mismatch_saves_private_reference_and_returns_one(self):
        rc,result,raw,perms,fixture,exists=self._call(compare_flag=True,wrong_after=True)
        self.assertEqual(rc,1)
        self.assertTrue(exists)
        self.assertEqual(result['mismatch_slot_indices'],list(range(9)))
        self.assertFalse(result['matches_supplied_nine_coefficients'])

    def test_external_capture_claim_is_not_authentication(self):
        rc,result,raw,perms,fixture,exists=self._call(source_synthetic=False)
        self.assertEqual(rc,0)
        self.assertEqual(fixture['source'],'external_ps1_capture_claim')
        self.assertFalse(result['ps1_capture_authenticity_independently_verified'])

    def test_invalid_json_is_generic_and_does_not_write(self):
        rc,result,raw,perms,fixture,exists=self._call(malformed=True)
        self.assertEqual(rc,2)
        self.assertFalse(exists)
        self.assertEqual(result['status'],'invalid_capture_or_output')
        self.assertNotIn('secret-original-state',str(result))

    def test_existing_reference_is_not_overwritten(self):
        rc,result,raw,perms,fixture,exists=self._call(already_exists=True)
        self.assertEqual(rc,2)
        self.assertEqual(raw,'EXISTING SECRET')
        self.assertFalse(result['private_values_emitted'])

    def test_reports_are_machine_readable_json_only(self):
        rc,result,raw,perms,fixture,exists=self._call()
        self.assertTrue(result['capture_package_prepared'])
        self.assertNotIn('EXE',str(result))
        self.assertNotIn('before.bin',str(result))
        self.assertNotIn('0x8001',str(result))

    def test_no_plaintext_matrix_or_registers_appear_in_stdout(self):
        rc,result,raw,perms,fixture,exists=self._call(compare_flag=True)
        self.assertNotIn(str([4096]*9),str(result))
        self.assertNotIn('data_hex',str(result))
        self.assertNotIn('gpr',str(result))


if __name__=='__main__':unittest.main()
