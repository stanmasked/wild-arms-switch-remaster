"""Synthetic contract tests for the local fail-closed host regression gate."""
import contextlib
from io import StringIO
import json
import unittest

from tools.audit_ps1_regression_gate import FOCUSED_MODULES, SCHEMA, run


class FakeLoader:
    def __init__(self, failing=False):
        self.failing = failing
        self.names = []

    def loadTestsFromName(self, name):
        self.names.append(name)
        failing = self.failing

        class Case(unittest.TestCase):
            def runTest(self):
                if failing:
                    print('PRIVATE_RAM_0x80010000')
                    raise AssertionError('PRIVATE_RAM_0x80010000')
        return unittest.TestSuite([Case()])


class HostRegressionGateTests(unittest.TestCase):
    def test_all_fixed_modules_selected_once(self):
        loader = FakeLoader()
        result = run(loader=loader)
        self.assertTrue(result['passed'])
        self.assertEqual(result['tests_run'], len(FOCUSED_MODULES))
        self.assertEqual(result['module_count'], len(FOCUSED_MODULES))
        self.assertEqual(tuple(loader.names), FOCUSED_MODULES)
        self.assertEqual(result['schema'], SCHEMA)

    def test_only_declared_module_selection_allowed(self):
        for modules in ((), ['tests.test_mips_caller_cfg_sources'],
                        ('evil.module',), (FOCUSED_MODULES[0],) * 2):
            with self.subTest(modules=modules), self.assertRaises(ValueError):
                run(loader=FakeLoader(), modules=modules)

    def test_failure_is_nonzero_sanitized_summary(self):
        captured = StringIO()
        with contextlib.redirect_stdout(captured):
            output = run(loader=FakeLoader(failing=True))
        self.assertEqual(captured.getvalue(), '')
        self.assertFalse(output['passed'])
        self.assertEqual(output['failures'], len(FOCUSED_MODULES))
        self.assertEqual(output['errors'], 0)
        self.assertNotIn('PRIVATE_RAM', json.dumps(output))
        self.assertFalse(output['private_failure_details_emitted'])

    def test_one_fixed_module_is_allowed(self):
        loader = FakeLoader()
        output = run(loader=loader, modules=(FOCUSED_MODULES[-1],))
        self.assertTrue(output['passed'])
        self.assertEqual(output['module_count'], 1)
        self.assertEqual(output['tests_run'], 1)

    def test_never_claims_game_or_switch_equivalence(self):
        result = run(loader=FakeLoader())
        self.assertFalse(result['original_ps1_equivalence_proven'])
        self.assertFalse(result['nintendo_switch_build_verified'])


if __name__ == '__main__':
    unittest.main()
