"""Safe command-line contract, return codes and private diagnostic discipline."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tools.audit_ps1_matrix_reference import main
from tests.test_mips_ps1_matrix_reference import fixture, synthetic_program


class MatrixReferenceCLITests(unittest.TestCase):
    def execute_cli(self, blob, reference_text):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'private_game.exe'
            ref=Path(temp)/'private_capture.json'
            exe.write_bytes(blob)
            ref.write_text(reference_text,encoding='utf-8')
            out=StringIO()
            with contextlib.redirect_stdout(out):
                code=main(['--exe',str(exe),'--reference',str(ref)])
            return code,json.loads(out.getvalue()),out.getvalue()

    def test_cli_matches_nine_synthetic_coefficients(self):
        blob=synthetic_program()
        code,data,out=self.execute_cli(blob,json.dumps(fixture(blob)))
        self.assertEqual(code,0)
        self.assertTrue(data['matches_supplied_nine_coefficients'])
        self.assertEqual(data['matching_coefficient_count'],9)
        self.assertNotIn('4096',out)
        self.assertNotIn('private_game.exe',out)

    def test_cli_returns_one_for_numeric_mismatch(self):
        blob=synthetic_program()
        ref=fixture(blob);ref['expected_matrix_s16'][4]=-32
        code,data,out=self.execute_cli(blob,json.dumps(ref))
        self.assertEqual(code,1)
        self.assertEqual(data['mismatch_slot_indices'],[4])
        self.assertNotIn('-32',out)

    def test_cli_returns_one_if_not_all_nine_sh_written(self):
        blob=synthetic_program(slots=5)
        code,data,_=self.execute_cli(blob,json.dumps(fixture(blob)))
        self.assertEqual(code,1)
        self.assertFalse(data['coefficient_comparison_performed'])
        self.assertEqual(data['final_halfword_slots_written_by_sh'],5)

    def test_cli_invalid_json_does_not_echo_capture(self):
        blob=synthetic_program()
        code,data,out=self.execute_cli(blob,'{"secret":"secret-angle-123",')
        self.assertEqual(code,2)
        self.assertEqual(data['status'],'invalid_reference_or_executable')
        self.assertNotIn('secret-angle-123',out)

    def test_cli_wrong_sha_returns_generic_failure(self):
        blob=synthetic_program();ref=fixture(blob);ref['exe_sha256']='f'*64
        code,data,out=self.execute_cli(blob,json.dumps(ref))
        self.assertEqual(code,2)
        self.assertNotIn('exe_sha256',out)
        self.assertFalse(data['private_values_emitted'])

    def test_cli_truncated_executable_does_not_print_executable_bytes(self):
        blob=b'PS-X EXE\x00private source only'
        code,data,out=self.execute_cli(blob,json.dumps(fixture(synthetic_program())))
        self.assertEqual(code,2)
        self.assertEqual(data['status'],'invalid_reference_or_executable')
        self.assertNotIn('private source only',out)

    def test_cli_external_capture_claim_stays_unverified(self):
        blob=synthetic_program()
        f=fixture(blob,source='external_ps1_capture_claim')
        code,result,_=self.execute_cli(blob,json.dumps(f))
        self.assertEqual(code,0)
        self.assertTrue(result['supplied_reference_is_claimed_external_capture'])
        self.assertFalse(result['external_ps1_capture_authenticity_independently_verified'])

    def test_cli_argument_parser_requires_two_files(self):
        with contextlib.redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exc:
            main([])
        self.assertEqual(exc.exception.code,2)

if __name__=='__main__':unittest.main()
