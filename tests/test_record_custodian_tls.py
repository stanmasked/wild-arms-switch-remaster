"""Synthetic-only mutual TLS 1.3 custodian transport tests (loopback)."""
from concurrent.futures import ThreadPoolExecutor
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.test_record_atomic_verifier import FIXED_NOW, NONCE_A, NONCE_B
from tools.audit_record_atomic_verifier import issue as legacy_issue
from tools.audit_record_anchor_handoff import deposit, _read_latest
from tools.audit_record_verifier_checkpoint import save_checkpoint
from tools.audit_record_signed_custodian import verify_signed
from tools.audit_record_custodian_tls import (
    REQUEST_SCHEMA, RESPONSE_SCHEMA, MAX_FRAME,
    _tls_context, _receive, _send, _process, _peer_pin, exchange, serve_one, main,
)


def openssl(*args):
    subprocess.run(['openssl', *map(str, args)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=15)


class MutualTlsCustodianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys_tmp = tempfile.TemporaryDirectory()
        base = Path(cls.keys_tmp.name)
        cls.ca = base / 'ca.pem'
        ca_key = base / 'ca.key'
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', ca_key, '-out', cls.ca, '-days', '1',
                '-subj', '/CN=Test Certificate Authority')
        for role in ('server', 'client'):
            key = base / (role + '.key')
            request = base / (role + '.csr')
            cert = base / (role + '.pem')
            extensions = base / (role + '.ext')
            ext = 'subjectAltName=DNS:localhost\nextendedKeyUsage='
            extensions.write_text(
                ext + ('serverAuth' if role == 'server' else 'clientAuth') + '\n')
            openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout',
                    key, '-out', request, '-subj', '/CN=' + role)
            openssl('x509', '-req', '-in', request, '-CA', cls.ca,
                    '-CAkey', ca_key, '-CAcreateserial',
                    '-out', cert, '-days', '1', '-extfile', extensions)
            key.chmod(0o600)
            cert.chmod(0o600)
            setattr(cls, role + '_key', key)
            setattr(cls, role + '_cert', cert)
            setattr(cls, role + '_pin',
                    hashlib.sha256(ssl.PEM_cert_to_DER_cert(
                        cert.read_text())).hexdigest())
        cls.ca.chmod(0o600)
        ca_key.chmod(0o600)
        # The custody signature uses a distinct Ed25519 key, not the TLS key.
        cls.sign_key = base / 'signer.key'
        cls.sign_pub = base / 'signer.pem'
        openssl('genpkey', '-algorithm', 'ed25519', '-out', cls.sign_key)
        openssl('pkey', '-in', cls.sign_key, '-pubout', '-out', cls.sign_pub)
        cls.sign_key.chmod(0o600)
        cls.sign_pub.chmod(0o600)
        cls.sign_pub_pin = hashlib.sha256(cls.sign_pub.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.keys_tmp.cleanup()

    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        root = Path(context.name)
        self.v = root / 'verifier'
        self.c = root / 'custodian'
        self.v.mkdir(mode=0o700)
        self.c.mkdir(mode=0o700)
        self.verifier = self.v / 'capture.sqlite'
        self.custody = self.c / 'custody.sqlite'
        self.offer_counter = 0
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_A):
            legacy_issue(self.verifier, now=FIXED_NOW)
        self.make_offer_and_deposit()
        self.tag = 'custodian_reference'

    def make_offer_and_deposit(self):
        self.offer_counter += 1
        offer = self.v / ('checkpoint%d.json' % self.offer_counter)
        save_checkpoint(self.verifier, offer)
        deposit(self.custody, offer.read_bytes())
        return offer.read_bytes()

    def new_offer(self):
        with patch('tools.audit_record_atomic_verifier.secrets.token_hex',
                   return_value=NONCE_B):
            legacy_issue(self.verifier, now=FIXED_NOW+1)
        self.offer_counter += 1
        offer = self.v / ('checkpoint%d.json' % self.offer_counter)
        save_checkpoint(self.verifier, offer)
        return offer.read_bytes()

    def run_channel(self, *, action='latest', checkpoint=None,
                    server_pin=None, client_pin=None, signer_pin=None,
                    tag=None, client_key=None, client_cert=None,
                    expected_head=None):
        if action == 'deposit' and expected_head is None:
            prior = _read_latest(self.custody)
            expected_head = (prior[0], prior[3])
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(4)
            port = listener.getsockname()[1]
            with ThreadPoolExecutor(max_workers=1) as executor:
                done = executor.submit(
                    serve_one, listener, self.custody,
                    self.sign_key, self.server_cert, self.server_key, self.ca,
                    self.client_pin if client_pin is None else client_pin,
                    tag=self.tag)
                try:
                    response = exchange(
                        '127.0.0.1', port, hostname='localhost',
                        cert=self.client_cert if client_cert is None else client_cert,
                        key=self.client_key if client_key is None else client_key,
                        ca=self.ca,
                        server_cert_sha256=self.server_pin
                        if server_pin is None else server_pin,
                        pinned_signing_public_key=self.sign_pub,
                        signing_public_key_sha256=self.sign_pub_pin
                        if signer_pin is None else signer_pin,
                        tag=self.tag if tag is None else tag,
                        action=action, checkpoint_raw=checkpoint,
                        expected_sequence=expected_head[0] if expected_head else None,
                        expected_receipt_sha256=expected_head[1] if expected_head else None)
                except Exception:
                    result = done.result(timeout=6)
                    raise
                accepted = done.result(timeout=6)
            return response, accepted

    def test_latest_roundtrip_requires_both_tls_pins_and_ed25519(self):
        (raw, signed, seq), ok = self.run_channel()
        self.assertTrue(ok)
        self.assertEqual(seq, 1)
        receipt = json.loads(verify_signed(
            signed, self.sign_pub, self.sign_pub_pin, custodian_tag=self.tag))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         receipt['checkpoint_sha256'])
        self.assertNotIn(NONCE_A, signed.decode())

    def test_deposit_then_latest_and_idempotent_retry(self):
        offered = self.new_offer()
        old_head = _read_latest(self.custody)
        (_, _, sequence), ok = self.run_channel(
            action='deposit', checkpoint=offered)
        self.assertTrue(ok)
        self.assertEqual(sequence, 2)
        (checkpoint, _, again), ok = self.run_channel(
            action='deposit', checkpoint=offered,
            expected_head=(old_head[0], old_head[3]))
        self.assertTrue(ok)
        self.assertEqual(again, 2)
        self.assertEqual(checkpoint, offered)
        self.assertEqual(self.run_channel()[0][2], 2)

    def test_stale_offer_refused_by_custodian_history(self):
        old = (self.v / 'checkpoint1.json').read_bytes()
        self.run_channel(action='deposit', checkpoint=self.new_offer())
        with self.assertRaisesRegex(ValueError, 'refused'):
            self.run_channel(action='deposit', checkpoint=old)
        self.assertEqual(_read_latest(self.custody)[0], 2)

    def test_wrong_tls_server_pin_refused_before_checkpoint_send(self):
        offered = self.new_offer()
        with self.assertRaisesRegex(ValueError, 'peer certificate'):
            self.run_channel(action='deposit', checkpoint=offered,
                             server_pin='f'*64)
        self.assertEqual(_read_latest(self.custody)[0], 1)

    def test_wrong_tls_client_pin_refused_by_custodian(self):
        with self.assertRaises((ValueError, OSError, ssl.SSLError)):
            self.run_channel(client_pin='f'*64)

    def test_wrong_ed25519_signing_pin_rejects_transport_response(self):
        with self.assertRaisesRegex(ValueError, 'pin mismatch'):
            self.run_channel(signer_pin='f'*64)

    def test_wrong_signed_custodian_identity_rejected(self):
        with self.assertRaises(ValueError):
            self.run_channel(tag='different-custodian')

    def test_malformed_base64_and_oversized_request_rejected(self):
        for candidate in ('not-base64!', ''):
            with self.subTest(candidate=candidate):
                request = {
                    'schema': REQUEST_SCHEMA, 'action': 'deposit',
                    'request_id': 'a'*32, 'checkpoint_b64': candidate,
                }
                with self.assertRaises(ValueError):
                    _process(request, self.custody, self.sign_key, self.tag)
        with self.assertRaises(ValueError):
            _process({'schema': REQUEST_SCHEMA, 'action': 'latest',
                      'request_id': 'a'*32, 'surprise': 1},
                     self.custody, self.sign_key, self.tag)

    def test_bad_nonce_and_action_rejected(self):
        for action, nonce in (('latest', 'X'*32), ('unknown', 'a'*32)):
            with self.assertRaises(ValueError):
                _process({'schema': REQUEST_SCHEMA, 'action': action,
                          'request_id': nonce},
                         self.custody, self.sign_key, self.tag)

    def test_missing_client_identity_refused_by_tls(self):
        ctx = ssl.create_default_context(cafile=str(self.ca))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.settimeout(4)
            with ThreadPoolExecutor(max_workers=1) as executor:
                task = executor.submit(
                    serve_one, listener, self.custody, self.sign_key,
                    self.server_cert, self.server_key, self.ca,
                    self.client_pin, tag=self.tag)
                with self.assertRaises((ssl.SSLError, ValueError, OSError)):
                    with socket.create_connection(listener.getsockname()) as raw:
                        with ctx.wrap_socket(raw, server_hostname='localhost') as tls:
                            _send(tls, {'schema': REQUEST_SCHEMA,
                                        'action': 'latest', 'request_id': 'a'*32})
                            _receive(tls)
                self.assertFalse(task.result(timeout=6))

    def test_lost_server_reply_after_durable_deposit_recovers(self):
        offered = self.new_offer()
        old_head = _read_latest(self.custody)
        import tools.audit_record_custodian_tls as channel
        process = channel._process
        def disappear_after_commit(*args):
            process(*args)
            raise OSError('simulated break after durable custodian commit')
        with patch('tools.audit_record_custodian_tls._process',
                   side_effect=disappear_after_commit):
            with self.assertRaises((ValueError, OSError, ssl.SSLError)):
                self.run_channel(action='deposit', checkpoint=offered)
        self.assertEqual(_read_latest(self.custody)[0], 2)
        (_, _, seq), ok = self.run_channel(
            action='deposit', checkpoint=offered,
            expected_head=(old_head[0], old_head[3]))
        self.assertEqual(seq, 2)
        self.assertTrue(ok)

    def test_reply_request_id_binding_rejects_replayed_response(self):
        import tools.audit_record_custodian_tls as channel
        handler = channel._process
        def replayed(*args):
            response = handler(*args)
            response['request_id'] = 'f'*32
            return response
        with patch('tools.audit_record_custodian_tls._process', side_effect=replayed):
            with self.assertRaisesRegex(ValueError, 'replayed'):
                self.run_channel()

    def test_tls_private_credential_paths_are_guarded(self):
        shared = self.v / 'tls-cert-link.pem'
        shared.symlink_to(self.client_cert)
        with self.assertRaises(ValueError):
            _tls_context(shared, self.client_key, self.ca, server=False)

    def test_cli_unknown_private_pin_is_redacted(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['latest', '127.0.0.1', '12345', 'localhost',
                         str(self.client_cert), str(self.client_key),
                         str(self.ca), 'broken-private-pin',
                         str(self.sign_pub), self.sign_pub_pin,
                         str(self.v/'signed.json'), str(self.v/'state.json'),
                         '--custodian-tag', self.tag])
        self.assertEqual(code, 2)
        self.assertNotIn(self.sign_pub_pin, output.getvalue())
        self.assertNotIn('PRIVATE', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['error_code'],
                         'invalid_private_input_or_channel')


if __name__ == '__main__':
    unittest.main()
