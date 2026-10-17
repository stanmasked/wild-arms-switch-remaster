"""Synthetic metadata contract for safe GitHub Actions runner triage."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools.audit_actions_job_bootstrap import classify, main


class ActionsBootstrapTests(unittest.TestCase):
    def jobs(self, *items):
        return {'total_count': len(items), 'jobs': list(items)}

    def test_all_failure_jobs_before_runner_are_a_symptom_not_proof(self):
        data = self.jobs({'conclusion': 'failure', 'runner_name': '', 'steps': []},
                         {'conclusion': 'failure', 'runner_name': '', 'steps': []})
        r = classify(data)
        self.assertTrue(r['all_returned_failures_pre_runner'])
        self.assertEqual(r['failed_without_runner_or_steps'], 2)
        self.assertFalse(r['infrastructure_root_cause_proven'])
        self.assertFalse(r['test_failure_proven'])

    def test_recorded_steps_are_distinct_from_bootstrap_failure(self):
        data = self.jobs({'conclusion': 'failure', 'runner_name': 'runner1',
                          'steps': [{'conclusion': 'failure'}]},
                         {'conclusion': 'failure', 'runner_name': '', 'steps': []})
        r = classify(data)
        self.assertEqual(r['failed_with_recorded_steps'], 1)
        self.assertEqual(r['failed_without_runner_or_steps'], 1)
        self.assertFalse(r['all_returned_failures_pre_runner'])

    def test_missing_steps_is_unknown_not_pre_runner(self):
        data = self.jobs({'conclusion': 'failure', 'runner_name': ''})
        self.assertEqual(classify(data)['failed_without_sufficient_evidence'], 1)
        self.assertFalse(classify(data)['all_returned_failures_pre_runner'])

    def test_success_and_pending_are_not_failures(self):
        data = self.jobs({'conclusion': 'success', 'steps': []},
                         {'conclusion': None, 'status': 'queued'})
        self.assertEqual(classify(data)['failed_jobs'], 0)
        self.assertFalse(classify(data)['all_returned_failures_pre_runner'])

    def test_partial_page_never_claims_coverage_of_all_jobs(self):
        data = self.jobs({'conclusion': 'failure', 'steps': [], 'runner_name': ''})
        data['total_count'] = 5
        self.assertTrue(classify(data)['partial_job_page'])

    def test_private_fields_never_enter_report(self):
        private = 'SECRET_GUEST_PC_0x80010000'
        data = self.jobs({'conclusion': 'failure', 'steps': [],
                          'runner_name': '', 'name': private,
                          'html_url': private, 'id': 999})
        self.assertNotIn(private, json.dumps(classify(data)))
        self.assertNotIn('999', json.dumps(classify(data)))

    def test_invalid_shapes_fail_closed(self):
        for raw in ({}, [], {'total_count': True, 'jobs': []},
                    {'total_count': 0, 'jobs': [{}]},
                    {'total_count': 1, 'jobs': ['invalid']},
                    {'total_count': -1, 'jobs': []}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                classify(raw)

    def test_cli_does_not_print_private_payload(self):
        secret = 'MIPS_REGISTERS_PRIVATE'
        data = self.jobs({'conclusion': 'failure', 'runner_name': '',
                          'steps': [], 'name': secret})
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'jobs.json'
            src.write_text(json.dumps(data))
            stream = StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(main(['--jobs-json', str(src)]), 0)
            self.assertNotIn(secret, stream.getvalue())
            self.assertTrue(json.loads(stream.getvalue())['all_returned_failures_pre_runner'])

    def test_cli_invalid_json_prints_generic_error_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'private-metadata.json'
            src.write_text('{"SECRET_KEY":')
            stream = StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(main(['--jobs-json', str(src)]), 2)
            self.assertNotIn('SECRET_KEY', stream.getvalue())
            self.assertNotIn(str(src), stream.getvalue())


if __name__ == '__main__':
    unittest.main()
