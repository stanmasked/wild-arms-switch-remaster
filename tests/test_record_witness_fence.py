"""Stage-261 durable witness fencing and real mTLS claim/release regressions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import socket
import sqlite3
import unittest
from unittest.mock import patch

from tests.test_record_remote_recovery_witness import (
    RemoteRecoveryWitnessTests as PriorTLS,
)
from tests.test_record_custodian_tls import MutualTlsCustodianTests as TLSFixture
from tools.audit_record_remote_recovery_witness import (
    serve_one as witness_serve,
)
from tools.audit_record_remote_witness_fence import (
    _verify, handle, exchange_fence, fenced_custody_request,
    REQUEST_SCHEMA,
)
from tools.audit_record_recovery_witness import record, snapshot, _head
from tools.audit_record_anchor_handoff import _canonical, _read_latest
from tools.audit_record_witness_fence import (
    claim, release, require_unfenced, FenceConflict, _fence_row,
)
from tools.audit_record_custodian_tls import (
    serve_one as custody_serve, exchange as custody_exchange,
)

A = 'a'*32
B = 'b'*32
D1 = '1'*64
D2 = '2'*64


class WitnessFenceTests(unittest.TestCase):
    setUp = PriorTLS.setUp
    add_unwitnessed_recovery = PriorTLS.add_unwitnessed_recovery
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

    def head(self):
        rows = _head(self.witness_db)
        return rows[0], rows[2]

    def row(self):
        with sqlite3.connect(self.witness_db) as con:
            return _fence_row(con)

    def take(self, token=A, digest=D1):
        count, chain = self.head()
        return claim(self.witness_db, token, digest, count, chain)

    def test_single_owner_claim_and_exact_idempotent_retry(self):
        self.assertTrue(self.take())
        self.assertFalse(self.take())
        self.assertIsNotNone(self.row())
        self.assertTrue(release(self.witness_db, A, D1))
        self.assertIsNone(self.row())
        self.assertFalse(release(self.witness_db, A, D1))

    def test_competing_owner_denied_under_transactional_cas(self):
        self.take()
        with self.assertRaises(FenceConflict):
            self.take(B, D1)
        with self.assertRaises(FenceConflict):
            self.take(A, D2)
        self.assertEqual(self.row()[1], self.row()[1])

    def test_wrong_owner_cannot_release_active_fence(self):
        self.take()
        with self.assertRaises(FenceConflict):
            release(self.witness_db, B, D1)
        with self.assertRaises(FenceConflict):
            release(self.witness_db, A, D2)
        self.assertIsNotNone(self.row())

    def test_recovery_event_cannot_append_during_custody_fence(self):
        self.take()
        self.add_unwitnessed_recovery()
        raw = _canonical(snapshot(self.custody))
        with self.assertRaises(FenceConflict):
            record(self.witness_db, raw)
        self.assertEqual(self.head()[0], 0)
        self.assertTrue(release(self.witness_db, A, D1))
        self.assertEqual(record(self.witness_db, raw), (1, True))

    def test_cas_head_mismatch_denied_without_fence_mutation(self):
        with self.assertRaises(FenceConflict):
            claim(self.witness_db, A, D1, 1, 'f'*64)
        self.assertIsNone(self.row())

    def test_after_signed_witness_advance_stale_claim_refused(self):
        self.add_unwitnessed_recovery()
        record(self.witness_db, _canonical(snapshot(self.custody)))
        with self.assertRaises(FenceConflict):
            claim(self.witness_db, A, D1, 0, '0'*64)
        self.assertTrue(self.take())

    def test_two_parallel_claims_get_only_one_winner(self):
        def attempt(token):
            try:
                return self.take(token)
            except FenceConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as ex:
            results = list(ex.map(attempt, (A, B)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(None), 1)

    def test_active_fence_survives_reopened_database(self):
        self.take()
        with sqlite3.connect(self.witness_db) as con:
            self.assertIsNotNone(_fence_row(con))
        self.assertFalse(self.take())
        self.assertTrue(release(self.witness_db, A, D1))

    def test_malformed_private_schema_blocks_all_claims(self):
        with sqlite3.connect(self.witness_db) as con:
            con.execute('CREATE TABLE recovery_witness_fence(bad INTEGER)')
        with self.assertRaises(ValueError):
            self.take()
        with self.assertRaises(ValueError):
            release(self.witness_db, A, D1)

    def test_claim_and_release_signatures_bind_network_nonce(self):
        req = {
            'schema': REQUEST_SCHEMA, 'action': 'claim-head',
            'request_id': 'e'*32, 'fence_token': A,
            'custody_request_sha256': D1,
            'expected_count': 0, 'expected_chain_sha256': '0'*64,
        }
        reply = handle(req, self.witness_db, self.witness_sign_key,
                       self.witness_tag)
        self.assertEqual(_verify(reply, req, self.witness_tag,
                                 self.witness_pub, self.witness_pin)[0], 0)
        altered = dict(req, request_id='f'*32)
        with self.assertRaises(ValueError):
            _verify(reply, altered, self.witness_tag,
                    self.witness_pub, self.witness_pin)
        wrong = dict(reply, custody_request_sha256=D2)
        with self.assertRaises(ValueError):
            _verify(wrong, req, self.witness_tag,
                    self.witness_pub, self.witness_pin)
        self.assertTrue(release(self.witness_db, A, D1))

    def test_bad_public_pin_blocks_authenticated_claim(self):
        req = {
            'schema': REQUEST_SCHEMA, 'action': 'claim-head',
            'request_id': 'e'*32, 'fence_token': A,
            'custody_request_sha256': D1,
            'expected_count': 0, 'expected_chain_sha256': '0'*64,
        }
        response = handle(req, self.witness_db,
                          self.witness_sign_key, self.witness_tag)
        with self.assertRaises(ValueError):
            _verify(response, req, self.witness_tag,
                    self.witness_pub, 'f'*64)

    def tls_opts(self, port):
        return {
            'witness_host': '127.0.0.1', 'witness_port': port,
            'hostname': 'localhost', 'cert': self.client_cert,
            'key': self.client_key, 'ca': self.ca,
            'server_pin': self.server_pin, 'public_key': self.witness_pub,
            'public_pin': self.witness_pin, 'tag': self.witness_tag,
        }

    def test_real_mutual_tls_claim_holds_until_local_commit_then_releases(self):
        # One fresh-head and one conditional claim/release; all three
        # network exchanges independently validate both TLS endpoints.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(3)
            listener.settimeout(6)
            port = listener.getsockname()[1]
            def witness_server():
                return [
                    witness_serve(listener, self.witness_db,
                                  self.witness_sign_key, self.server_cert,
                                  self.server_key, self.ca, self.client_pin,
                                  tag=self.witness_tag)
                    for _ in range(3)]
            request = {
                'schema': 'wild-arms-ps1-mutual-tls-custodian-request-v1',
                'action': 'reserve',
                'request_id': 'e'*32, 'expected_sequence': 1,
                'expected_receipt_sha256': _read_latest(self.custody)[3],
                'reservation_token': A,
            }
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(witness_server)
                with fenced_custody_request(request, **self.tls_opts(port)) as head:
                    self.assertEqual(head[0], 0)
                    with sqlite3.connect(self.witness_db) as con:
                        self.assertIsNotNone(_fence_row(con))
                    self.add_unwitnessed_recovery()
                    with self.assertRaises(FenceConflict):
                        record(self.witness_db, _canonical(snapshot(self.custody)))
                self.assertTrue(all(future.result(timeout=9)))
        self.assertIsNone(self.row())
        self.assertEqual(record(self.witness_db,
                                _canonical(snapshot(self.custody))), (1, True))

    def test_fence_provider_does_not_release_early_on_custody_exception(self):
        # Exception handling still performs exact remote release AFTER
        # the local protected block is unwound.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(3)
            listener.settimeout(6)
            port=listener.getsockname()[1]
            def serving():
                return [witness_serve(
                    listener, self.witness_db, self.witness_sign_key,
                    self.server_cert, self.server_key, self.ca,
                    self.client_pin, tag=self.witness_tag) for _ in range(3)]
            request = {
                'schema': 'wild-arms-ps1-mutual-tls-custodian-request-v1',
                'action': 'reserve', 'request_id': 'd'*32,
                'expected_sequence': 1,
                'expected_receipt_sha256': _read_latest(self.custody)[3],
                'reservation_token': A,
            }
            with ThreadPoolExecutor(max_workers=1) as pool:
                server = pool.submit(serving)
                with self.assertRaisesRegex(RuntimeError, 'test rollback'):
                    with fenced_custody_request(request, **self.tls_opts(port)):
                        raise RuntimeError('test rollback')
                self.assertTrue(all(server.result(timeout=9)))
        self.assertIsNone(self.row())


if __name__ == '__main__':
    unittest.main()
