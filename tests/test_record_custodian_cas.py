"""Synthetic custodian CAS race tests: divergent verifier writers and lost replies."""
from concurrent.futures import ThreadPoolExecutor
import shutil
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import NONCE_A, NONCE_B, FIXED_NOW
from tools.audit_record_atomic_verifier import issue
from tools.audit_record_anchor_handoff import (
    deposit, _read_latest, HandoffRegression,
)
from tools.audit_record_verifier_checkpoint import save_checkpoint

NONCE_C = 'fedcba9876543210fedcba9876543210'


class CustodianCASTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.verifier = self.root / 'verifier'
        self.storage = self.root / 'custodian'
        self.verifier.mkdir(mode=0o700)
        self.storage.mkdir(mode=0o700)
        self.db = self.verifier / 'original.sqlite'
        self.custody = self.storage / 'head.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            issue(self.db, now=FIXED_NOW)
        self.root_state = self.snapshot(self.db, 'root')
        self.assertEqual(deposit(self.custody, self.root_state), (1, True))

    def snapshot(self, db, name):
        output = self.verifier / (name + '.json')
        save_checkpoint(db, output)
        return output.read_bytes()

    def divergent(self):
        first, second = self.verifier / 'first.sqlite', self.verifier / 'second.sqlite'
        shutil.copyfile(self.db, first)
        shutil.copyfile(self.db, second)
        first.chmod(0o600)
        second.chmod(0o600)
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            issue(first, now=FIXED_NOW+1)
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_C):
            issue(second, now=FIXED_NOW+1)
        return self.snapshot(first, 'first'), self.snapshot(second, 'second')

    def expected(self):
        row = _read_latest(self.custody)
        return {'expected_sequence': row[0],
                'expected_receipt_sha256': row[3]}

    def test_exact_retry_after_lost_reply_single_round(self):
        a, _ = self.divergent()
        expected = self.expected()
        self.assertEqual(deposit(self.custody, a, **expected), (2, True))
        self.assertEqual(deposit(self.custody, a, **expected), (2, False))
        self.assertEqual(_read_latest(self.custody)[0], 2)

    def test_second_writer_from_same_head_refused(self):
        a, b = self.divergent()
        expected = self.expected()
        self.assertEqual(deposit(self.custody, a, **expected), (2, True))
        with self.assertRaises(HandoffRegression):
            deposit(self.custody, b, **expected)
        self.assertEqual(_read_latest(self.custody)[4], a)

    def test_concurrent_different_checkpoint_only_one_wins(self):
        a, b = self.divergent()
        expected = self.expected()
        def contender(blob):
            try:
                return deposit(self.custody, blob, **expected)
            except HandoffRegression:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, (a, b)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(_read_latest(self.custody)[0], 2)
        self.assertIn(_read_latest(self.custody)[4], (a, b))

    def test_parallel_exact_retries_one_new_entry(self):
        a, _ = self.divergent()
        expected = self.expected()
        with ThreadPoolExecutor(max_workers=8) as pool:
            result = list(pool.map(lambda _: deposit(self.custody, a, **expected),
                                   range(8)))
        self.assertEqual(sum(is_new for _, is_new in result), 1)
        self.assertTrue(all(seq == 2 for seq, _ in result))

    def test_missing_expected_one_value_refused(self):
        a, _ = self.divergent()
        for args in (
            {'expected_sequence': 1},
            {'expected_receipt_sha256': self.expected()['expected_receipt_sha256']},
            {'expected_sequence': True, 'expected_receipt_sha256': 'f'*64},
            {'expected_sequence': 1, 'expected_receipt_sha256': 'not-a-hash'},
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    deposit(self.custody, a, **args)
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_incorrect_prior_hash_or_sequence_refused(self):
        a, _ = self.divergent()
        with self.assertRaises(HandoffRegression):
            deposit(self.custody, a, expected_sequence=1,
                    expected_receipt_sha256='f'*64)
        with self.assertRaises(HandoffRegression):
            deposit(self.custody, a, expected_sequence=2,
                    expected_receipt_sha256=self.expected()['expected_receipt_sha256'])
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_retry_after_another_committed_round_refused(self):
        a, _ = self.divergent()
        expected = self.expected()
        deposit(self.custody, a, **expected)
        # Add third state by extending the chosen verifier DB from its own
        # current state, rather than constructing an incompatible fork.
        first_db = self.verifier / 'first.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_C):
            issue(first_db, now=FIXED_NOW+2)
        third = self.snapshot(first_db, 'third')
        self.assertEqual(deposit(self.custody, third, **self.expected()), (3, True))
        with self.assertRaises(HandoffRegression):
            deposit(self.custody, a, **expected)
        self.assertEqual(_read_latest(self.custody)[0], 3)

    def test_root_offer_not_accepted_as_cas_next_round(self):
        expected = self.expected()
        with self.assertRaises(HandoffRegression):
            deposit(self.custody, self.root_state, **expected)
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_legacy_deposit_remains_available_but_not_cas(self):
        a, _ = self.divergent()
        self.assertEqual(deposit(self.custody, a), (2, True))
        self.assertEqual(deposit(self.custody, a), (2, False))
        # Operators must restrict legacy direct deposit access. This
        # regression documents that stage-253 CAS is opt-in on the API.
        self.assertEqual(_read_latest(self.custody)[0], 2)


if __name__ == '__main__':
    unittest.main()
