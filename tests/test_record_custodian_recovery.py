"""Synthetic tests for independently signed, audited custody orphan recovery."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import FIXED_NOW, NONCE_A, NONCE_B
from tools.audit_record_atomic_verifier import issue
from tools.audit_record_anchor_handoff import deposit, _read_latest
from tools.audit_record_custodian_reservation import (
    reserve, reservation_row, ReservationConflict)
from tools.audit_record_custodian_recovery import (
    approve, audit_history, prepare, recover, RecoveryConflict, main,
    MAX_REQUEST, MAX_APPROVAL)
from tools.audit_record_verifier_checkpoint import save_checkpoint

TOKEN_A = 'a' * 32
TOKEN_B = 'b' * 32


def openssl(*args):
    subprocess.run(['openssl', *map(str, args)], check=True, timeout=15,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class CustodianRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.client_dir = root / 'verifier'
        self.custodian_dir = root / 'custodian'
        self.admin_dir = root / 'admins'
        for directory in (self.client_dir, self.custodian_dir, self.admin_dir):
            directory.mkdir(mode=0o700)
        self.db = self.client_dir / 'verifier.sqlite'
        self.custody = self.custodian_dir / 'custody.sqlite'
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            issue(self.db, now=FIXED_NOW)
        offer = self.client_dir / 'genesis.json'
        save_checkpoint(self.db, offer)
        self.assertEqual(deposit(self.custody, offer.read_bytes()), (1, True))
        head = _read_latest(self.custody)
        self.assertTrue(reserve(self.custody, head[0], head[3], TOKEN_A))
        self.keys = {}
        for name in ('alice', 'bob', 'mallory'):
            secret = self.admin_dir / (name + '.key')
            public = self.admin_dir / (name + '.pub')
            openssl('genpkey', '-algorithm', 'ed25519', '-out', secret)
            openssl('pkey', '-in', secret, '-pubout', '-out', public)
            secret.chmod(0o600)
            public.chmod(0o600)
            self.keys[name] = (
                secret, public, hashlib.sha256(public.read_bytes()).hexdigest())
        self.counter = 0

    def proposal(self):
        self.counter += 1
        path = self.custodian_dir / ('request-%d.json' % self.counter)
        self.assertEqual(prepare(self.custody, path), _read_latest(self.custody)[0])
        return path.read_bytes()

    def signs(self, data, names=('alice', 'bob')):
        out = []
        for name in names:
            self.counter += 1
            file = self.admin_dir / ('approval-%d.json' % self.counter)
            approve(data, name, self.keys[name][0], file)
            out.append(file.read_bytes())
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        return tuple(out)

    def recover(self, data, signatures, names=('alice', 'bob')):
        a, b = names
        return recover(
            self.custody, data, signatures[0], signatures[1],
            a, self.keys[a][1], self.keys[a][2],
            b, self.keys[b][1], self.keys[b][2])

    def journal(self):
        with sqlite3.connect(self.custody) as con:
            return audit_history(con)

    def new_checkpoint(self):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            issue(self.db, now=FIXED_NOW + 1)
        p = self.client_dir / 'future.json'
        save_checkpoint(self.db, p)
        return p.read_bytes()

    def test_two_distinct_signers_retire_reservation_atomically(self):
        request = self.proposal()
        signatures = self.signs(request)
        self.assertEqual(self.recover(request, signatures), 1)
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))
        self.assertEqual(len(self.journal()), 1)
        self.assertEqual(_read_latest(self.custody)[0], 1)
        head = _read_latest(self.custody)
        self.assertTrue(reserve(self.custody, head[0], head[3], TOKEN_B))

    def test_old_owner_cannot_deposit_after_recovery(self):
        request = self.proposal()
        self.recover(request, self.signs(request))
        head = _read_latest(self.custody)
        with self.assertRaises(ReservationConflict):
            deposit(self.custody, self.new_checkpoint(),
                    expected_sequence=head[0],
                    expected_receipt_sha256=head[3],
                    reservation_token=TOKEN_A)
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_unreserved_legacy_write_still_blocked_after_recovery(self):
        request = self.proposal()
        self.recover(request, self.signs(request))
        with self.assertRaises(ReservationConflict):
            deposit(self.custody, self.new_checkpoint())
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_missing_second_approval_fails_without_retirement(self):
        data = self.proposal()
        a, b = self.signs(data)
        with self.assertRaises(ValueError):
            self.recover(data, (a, a))
        self.assertEqual(self.journal(), [])
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'reserved')

    def test_swapped_admin_approval_rejected(self):
        data = self.proposal()
        a, b = self.signs(data)
        with self.assertRaises(ValueError):
            self.recover(data, (b, a))
        self.assertEqual(self.journal(), [])

    def test_same_pinned_key_two_admin_names_rejected(self):
        data = self.proposal()
        a, _ = self.signs(data)
        alice = self.keys['alice']
        with self.assertRaises(ValueError):
            recover(self.custody, data, a, a,
                    'alice', alice[1], alice[2],
                    'alice_2', alice[1], alice[2])
        self.assertEqual(self.journal(), [])

    def test_unpinned_public_key_rejected(self):
        data = self.proposal()
        a, b = self.signs(data)
        original = self.keys['bob']
        self.keys['bob'] = (original[0], original[1], 'f' * 64)
        with self.assertRaises(ValueError):
            self.recover(data, (a, b))
        self.assertEqual(self.journal(), [])

    def test_approval_for_different_request_nonce_rejected(self):
        original = self.proposal()
        approvals = self.signs(original)
        another = self.proposal()
        with self.assertRaises(ValueError):
            self.recover(another, approvals)
        self.assertEqual(self.journal(), [])

    def test_changed_reservation_token_after_approval_fails_closed(self):
        data = self.proposal()
        approvals = self.signs(data)
        head = _read_latest(self.custody)
        # Simulate privileged database mutation, which must not be
        # authorized by the old approvals.
        with sqlite3.connect(self.custody) as con:
            con.execute("UPDATE custodian_reservation SET token_sha256=?",
                        ('f'*64,))
        with self.assertRaises(RecoveryConflict):
            self.recover(data, approvals)
        self.assertEqual(self.journal(), [])

    def test_committed_reservation_never_recoverable(self):
        head = _read_latest(self.custody)
        deposit(self.custody, self.new_checkpoint(),
                expected_sequence=head[0], expected_receipt_sha256=head[3],
                reservation_token=TOKEN_A)
        with self.assertRaises(RecoveryConflict):
            self.proposal()

    def test_concurrent_double_recovery_has_single_winner(self):
        data = self.proposal()
        approvals = self.signs(data)
        def attempt(_):
            try:
                return self.recover(data, approvals)
            except RecoveryConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(outcomes.count(1), 1)
        self.assertEqual(outcomes.count(None), 1)
        self.assertEqual(len(self.journal()), 1)

    def test_sequential_approved_recoveries_form_hash_chain(self):
        one = self.proposal()
        self.assertEqual(self.recover(one, self.signs(one)), 1)
        head = _read_latest(self.custody)
        self.assertTrue(reserve(self.custody, head[0], head[3], TOKEN_B))
        two = self.proposal()
        self.assertEqual(self.recover(two, self.signs(two)), 2)
        events = self.journal()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1][5], events[0][6])

    def test_corrupt_recovery_journal_blocks_next_reserve(self):
        data = self.proposal()
        self.recover(data, self.signs(data))
        with sqlite3.connect(self.custody) as con:
            con.execute(
                'UPDATE custodian_recovery_history SET event_sha256=?',
                ('f'*64,))
        head = _read_latest(self.custody)
        with self.assertRaises(ValueError):
            reserve(self.custody, head[0], head[3], TOKEN_B)
        with self.assertRaises(ValueError):
            deposit(self.custody, self.new_checkpoint())
        with self.assertRaises(ValueError):
            self.proposal()

    def test_invalid_request_and_approval_are_refused(self):
        data = self.proposal()
        approvals = self.signs(data)
        variants = (
            b'', b'x'*(MAX_REQUEST+1), b'{"schema":"a","schema":"b"}',
            data.replace(b'irrecoverable-reservation-token', b'auto-expire'),
        )
        for payload in variants:
            with self.subTest(payload=payload[:30]):
                with self.assertRaises(ValueError):
                    self.recover(payload, approvals)
        self.assertEqual(len(self.journal()), 0)

    def test_invalid_private_signer_file_is_refused(self):
        data = self.proposal()
        secret = self.keys['alice'][0]
        secret.chmod(0o644)
        with self.assertRaises(ValueError):
            approve(data, 'alice', secret, self.admin_dir/'bad.json')
        secret.chmod(0o600)

    def test_cli_success_and_redacted_replay_refusal(self):
        private_request = self.custodian_dir / 'private-request.json'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['prepare', str(self.custody),
                                   str(private_request)]), 0)
        self.assertTrue(json.loads(out.getvalue())['private_recovery_request_prepared'])
        sig_paths = []
        for name in ('alice', 'bob'):
            p = self.admin_dir / (name+'-cli.json')
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(['approve', str(private_request), name,
                             str(self.keys[name][0]), str(p)])
            self.assertEqual(code, 0)
            sig_paths.append(p)
        args = [
            'recover', str(self.custody), str(private_request),
            *(str(p) for p in sig_paths),
            'alice', str(self.keys['alice'][1]), self.keys['alice'][2],
            'bob', str(self.keys['bob'][1]), self.keys['bob'][2],
        ]
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(main(args), 0)
        self.assertTrue(json.loads(out.getvalue())['orphan_reservation_retired'])
        self.assertNotIn(self.keys['alice'][2], out.getvalue())
        self.assertNotIn(TOKEN_A, out.getvalue())
        with contextlib.redirect_stdout(out := io.StringIO()):
            self.assertEqual(main(args), 1)
        self.assertTrue(json.loads(out.getvalue())[
            'recovery_refused_due_to_changed_state'])


if __name__ == '__main__':
    unittest.main()
