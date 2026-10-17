"""Bounded, privacy-safe host regression gate for PS1 audit modules.

Runs only synthetic host tests. Never claims hardware or Switch equivalence.
Private traceback strings and test stdout/stderr never enter the JSON output.
"""
import argparse
import contextlib
import io
import json
import unittest

SCHEMA = 'wild-arms-ps1-host-regression-gate-v1'
FOCUSED_MODULES = (
    'tests.test_gp0_matrix_context_cfg',
    'tests.test_gp0_matrix_context_sources',
    'tests.test_mips_caller_cfg_sources',
    'tests.test_mips_cfg_probe_path',
    'tests.test_gp0_cfg_runtime_correlation',
    'tests.test_gp0_matrix_replay_preflight',
    'tests.test_verify_record_stride',
    'tests.test_mips_matrix_arithmetic_attribution',
    'tests.test_ps1_arithmetic_matrix_attribution',
)


class _Discard(io.TextIOBase):
    def write(self, text):
        return len(text)


def run(*, loader=None, modules=FOCUSED_MODULES):
    """Summarize tests without exposing errors, private RAM, or test output."""
    if (not isinstance(modules, tuple) or not modules or
            any(type(name) is not str or name not in FOCUSED_MODULES
                for name in modules) or len(set(modules)) != len(modules)):
        raise ValueError('invalid fixed host regression module selection')
    if loader is None:
        loader = unittest.TestLoader()
    result = unittest.TestResult()
    with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
        suite = unittest.TestSuite(loader.loadTestsFromName(name)
                                   for name in modules)
        suite.run(result)
    return {
        'schema': SCHEMA,
        'module_count': len(modules),
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'passed': bool(result.wasSuccessful() and result.testsRun > 0),
        'original_ps1_equivalence_proven': False,
        'nintendo_switch_build_verified': False,
        'private_failure_details_emitted': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Focused offline PS1 host regression gate')
    parser.parse_args(argv)
    report = run()
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
