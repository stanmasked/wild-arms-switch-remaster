import unittest
from tools.mips_input_sensitivity import compare_runs, probe_input_registers

OFFSETS=set(range(0,18,2))

def profile(value=0, *, returned=True, offsets=None, path=None):
    return {'returned':returned, 'written_offsets': OFFSETS if offsets is None else offsets,
            'visited': (1,2,3) if path is None else path,
            'coefficients':(value,)+(0,)*8}

class InputSensitivityTests(unittest.TestCase):
    def test_one_coeff_changed_out_of_nine(self):
        r=compare_runs(profile(0),profile(3))
        self.assertTrue(r['all_nine_coefficients_comparable'])
        self.assertEqual(r['changed_coefficient_count'],1)
        self.assertFalse(r['execution_path_changed'])

    def test_equal_coefficients_not_proof_of_independence(self):
        r=compare_runs(profile(),profile())
        self.assertEqual(r['changed_coefficient_count'],0)

    def test_paths_differ_with_same_coefficients(self):
        r=compare_runs(profile(),profile(path=(1,4,3)))
        self.assertTrue(r['execution_path_changed'])
        self.assertEqual(r['changed_coefficient_count'],0)

    def test_partial_matrix_is_not_numerically_comparable(self):
        r=compare_runs(profile(offsets={0}),profile(offsets={0,2}))
        self.assertFalse(r['all_nine_coefficients_comparable'])
        self.assertTrue(r['matrix_store_coverage_changed'])
        self.assertIsNone(r['changed_coefficient_count'])

    def test_nonreturning_variant_disables_comparison(self):
        r=compare_runs(profile(),profile(9,returned=False))
        self.assertFalse(r['both_returned_to_caller'])
        self.assertIsNone(r['changed_coefficient_count'])

    def test_probe_only_reports_aggregate_without_raw_values(self):
        calls=[]
        def run(register, delta):
            calls.append((register, delta))
            return profile(int(register==4))
        result=probe_input_registers(run)
        self.assertEqual(calls,[(None,0),(4,1),(6,1),(7,1)])
        self.assertEqual(result['tested_register_count'],3)
        self.assertEqual([x['changed_coefficient_count'] for x in result['observations']],
                         [1,0,0])
        self.assertFalse(result['original_gameplay_inputs_known'])
        self.assertNotIn('coefficients',result['observations'][0])

    def test_reject_nonowned_or_duplicate_registers(self):
        with self.assertRaises(ValueError):
            probe_input_registers(lambda reg: profile(),registers=(5,))
        with self.assertRaises(ValueError):
            probe_input_registers(lambda reg: profile(),registers=(4,4))
        with self.assertRaises(ValueError):
            probe_input_registers(lambda reg: profile(),delta=0)

if __name__=='__main__':
    unittest.main()
