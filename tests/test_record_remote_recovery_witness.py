"""Stage 260 synthetic network-only independent recovery-witness tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

from tests.test_record_custodian_tls import (
    MutualTlsCustodianTests as TLSFixture, openssl,
)
from tools.audit_record_custodian_tls import (
    serve_one as serve_custody, exchange,
)
from tools.audit_record_remote_recovery_witness import (
    _reply, _check_signed_reply, _body, _canonical, SIGN_DOMAIN,
    _send, _receive, fetch_head, serve_one as serve_witness,
)
from tools.audit_record_recovery_witness import (
    initialize, record, snapshot, _head,
)
from tools.audit_record_custodian_recovery import (
    _event, _event_hash, audit_history,
)
from tools.audit_record_custodian_reservation import reserve, reservation_row
from tools.audit_record_anchor_handoff import _read_latest

TOKEN = 'a'*32
ALT_TOKEN = 'b'*32


class RemoteRecoveryWitnessTests(unittest.TestCase):
    make_offer_and_deposit = TLSFixture.make_offer_and_deposit
    new_offer = TLSFixture.new_offer

    @classmethod
    def setUpClass(cls):
        TLSFixture.setUpClass()
        for field in ('ca', 'server_key', 'server_cert', 'server_pin',
                      'client_key', 'client_cert', 'client_pin',
                      'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, field, getattr(TLSFixture, field))

    @classmethod
    def tearDownClass(cls):
        TLSFixture.tearDownClass()

    def setUp(self):
        TLSFixture.setUp(self)
        self.w = self.v/'independent-witness'
        self.w.mkdir(mode=0o700)
        self.witness_db = self.w/'recovery.sqlite'
        self.witness_sign_key = self.w/'witness-private.key'
        self.witness_pub = self.w/'witness-public.pem'
        openssl('genpkey', '-algorithm', 'ed25519',
                '-out', self.witness_sign_key)
        openssl('pkey', '-in', self.witness_sign_key, '-pubout',
                '-out', self.witness_pub)
        self.witness_sign_key.chmod(0o600)
        self.witness_pub.chmod(0o600)
        self.witness_pin = hashlib.sha256(
            self.witness_pub.read_bytes()).hexdigest()
        self.witness_tag = 'independent_remote_witness_test'
        initialize(self.witness_db)

    def expected_remote(self, host, port, **overrides):
        fields = {
            'hostname': 'localhost',
            'cert': self.client_cert,
            'key': self.client_key,
            'ca': self.ca,
            'server_pin': self.server_pin,
            'pinned_witness_public_key': self.witness_pub,
            'witness_public_key_pin': self.witness_pin,
            'tag': self.witness_tag,
        }
        fields.update(overrides)
        return fetch_head(host, port, **fields)

    def witness_exchange(self, *, changes=None):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(5)
            port = listener.getsockname()[1]
            with ThreadPoolExecutor(max_workers=1) as executor:
                running = executor.submit(
                    serve_witness, listener,
                    self.witness_db, self.witness_sign_key,
                    self.server_cert, self.server_key, self.ca,
                    self.client_pin, tag=self.witness_tag)
                try:
                    head = self.expected_remote(
                        '127.0.0.1', port, **(changes or {}))
                except Exception:
                    running.result(timeout=7)
                    raise
                accepted = running.result(timeout=7)
        return head, accepted

    def custody_exchange(self, *, action, token, offered=None,
                         remote_failure=False):
        expected = _read_latest(self.custody)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as witness_listener, \
                socket.socket(socket.AF_INET, socket.SOCK_STREAM) as custody_listener:
            witness_listener.bind(('127.0.0.1', 0))
            custody_listener.bind(('127.0.0.1', 0))
            for listener in (witness_listener, custody_listener):
                listener.listen(1)
                listener.settimeout(5)
            witness_port = witness_listener.getsockname()[1]
            custody_port = custody_listener.getsockname()[1]
            def fetch():
                if remote_failure:
                    raise OSError('independent witness unavailable')
                return self.expected_remote('127.0.0.1', witness_port)
            with ThreadPoolExecutor(max_workers=2) as pool:
                witness_task = (
                    pool.submit(
                        serve_witness, witness_listener, self.witness_db,
                        self.witness_sign_key, self.server_cert,
                        self.server_key, self.ca, self.client_pin,
                        tag=self.witness_tag)
                    if not remote_failure else None)
                custody_task = pool.submit(
                    serve_custody, custody_listener,
                    self.custody, self.sign_key,
                    self.server_cert, self.server_key, self.ca,
                    self.client_pin, tag=self.tag,
                    remote_witness_provider=fetch)
                try:
                    payload = exchange(
                        '127.0.0.1', custody_port,
                        hostname='localhost', cert=self.client_cert,
                        key=self.client_key, ca=self.ca,
                        server_cert_sha256=self.server_pin,
                        pinned_signing_public_key=self.sign_pub,
                        signing_public_key_sha256=self.sign_pub_pin,
                        tag=self.tag, action=action,
                        checkpoint_raw=offered,
                        expected_sequence=expected[0],
                        expected_receipt_sha256=expected[3],
                        reservation_token=token)
                except Exception:
                    self.assertFalse(custody_task.result(timeout=7))
                    if witness_task is not None:
                        witness_task.result(timeout=7)
                    raise
                self.assertTrue(custody_task.result(timeout=7))
                self.assertTrue(witness_task.result(timeout=7))
        return payload

    def add_unwitnessed_recovery(self):
        anchor = _read_latest(self.custody)
        with sqlite3.connect(self.custody) as con:
            audit_history(con, create=True)
            expected = {
                'expected_sequence': anchor[0],
                'expected_receipt_sha256': anchor[3],
                'expected_token_sha256': 'e'*64,
            }
            event = _event(1, 'f'*64, expected, '0'*64)
            con.execute(
                'INSERT INTO custodian_recovery_history'
                ' (sequence,request_sha256,base_sequence,'
                'base_receipt_sha256,retired_token_sha256,'
                'previous_event_sha256,event_sha256)'
                ' VALUES(?,?,?,?,?,?,?)',
                (1, 'f'*64, expected['expected_sequence'],
                 expected['expected_receipt_sha256'], 'e'*64,
                 '0'*64, _event_hash(event)))

    def test_actual_mutual_tls_returns_signed_fresh_genesis_without_db_copy(self):
        head, accepted = self.witness_exchange()
        self.assertTrue(accepted)
        self.assertEqual(head[:3], (0, '0'*64, '0'*64))
        self.assertEqual(head[3], [])
        self.assertFalse((self.c/'recovery.sqlite').exists())

    def test_real_network_witness_guards_reservation_and_deposit(self):
        checkpoint = self.new_offer()
        prior = _read_latest(self.custody)
        self.assertEqual(self.custody_exchange(
            action='reserve', token=TOKEN)[2], 1)
        self.assertEqual(self.custody_exchange(
            action='deposit-reserved', token=TOKEN,
            offered=checkpoint)[2], 2)
        self.assertEqual(_read_latest(self.custody)[0], 2)
        with sqlite3.connect(self.custody) as con:
            self.assertEqual(reservation_row(con)[4], 'committed')

    def test_witness_offline_prevents_custody_mutation(self):
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.custody_exchange(
                action='reserve', token=TOKEN, remote_failure=True)
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))

    def test_unwitnessed_recovery_event_blocks_online_guard(self):
        self.add_unwitnessed_recovery()
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.custody_exchange(action='reserve', token=TOKEN)
        with sqlite3.connect(self.custody) as con:
            self.assertIsNone(reservation_row(con))
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_witness_records_recovery_then_online_guard_resumes(self):
        self.add_unwitnessed_recovery()
        current_snapshot = _canonical(snapshot(self.custody))
        self.assertEqual(record(self.witness_db, current_snapshot), (1, True))
        head, ok = self.witness_exchange()
        self.assertTrue(ok)
        self.assertEqual(head[0], 1)
        self.assertEqual(head[3], _head(self.witness_db)[3])
        self.assertEqual(
            self.custody_exchange(action='reserve', token=TOKEN)[2], 1)

    def test_response_replay_cannot_satisfy_new_challenge(self):
        old = '1'*32
        new = '2'*32
        answer = _reply(
            {'schema':'wild-arms-ps1-remote-recovery-witness-request-v1',
             'action':'fresh-head', 'request_id':old},
            self.witness_db, self.witness_sign_key, self.witness_tag)
        self.assertEqual(_check_signed_reply(
            answer, old, self.witness_tag,
            self.witness_pub, self.witness_pin)[0], 0)
        with self.assertRaisesRegex(ValueError, 'replayed'):
            _check_signed_reply(
                answer, new, self.witness_tag,
                self.witness_pub, self.witness_pin)

    def test_tampered_signed_event_fails_before_admission(self):
        nonce='a'*32
        answer=_reply({
            'schema':'wild-arms-ps1-remote-recovery-witness-request-v1',
            'action':'fresh-head','request_id':nonce},
            self.witness_db,self.witness_sign_key,self.witness_tag)
        answer['witness_chain_sha256']='f'*64
        with self.assertRaises(ValueError):
            _check_signed_reply(
                answer, nonce, self.witness_tag,
                self.witness_pub, self.witness_pin)

    def test_wrong_pinned_signer_and_identity_fail_closed(self):
        with self.assertRaises(ValueError):
            self.witness_exchange(changes={'witness_public_key_pin': 'f'*64})
        with self.assertRaises(ValueError):
            self.witness_exchange(changes={'tag': 'another-witness'})

    def test_wrong_tls_server_pin_rejects_before_request_sent(self):
        with self.assertRaises(ValueError):
            self.witness_exchange(changes={'server_pin':'f'*64})

    def test_distinct_signed_reply_rejects_unexpected_extra_fields(self):
        nonce='a'*32
        answer=_reply({
            'schema':'wild-arms-ps1-remote-recovery-witness-request-v1',
            'action':'fresh-head','request_id':nonce},
            self.witness_db,self.witness_sign_key,self.witness_tag)
        answer['unexpected']='anything'
        with self.assertRaisesRegex(ValueError, 'invalid or replayed'):
            _check_signed_reply(
                answer, nonce, self.witness_tag,
                self.witness_pub, self.witness_pin)


if __name__=='__main__':
    unittest.main()
