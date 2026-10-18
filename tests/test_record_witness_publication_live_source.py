"""Stage 263X synthetic offline service simulations; no live service assumed."""
import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from tools import audit_record_witness_publication_live_source as live
from tools.audit_record_witness_fence_reconciliation import _sign

URL = 'https://independent.example.org/heads/current'
SCOPE = 'private-wild-arms-publication-mirrors'
AUTHORITY = 'external-head-authority'
CHALLENGE = 'a' * 32


class LiveSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys_temp = tempfile.TemporaryDirectory()
        cls.keys = []
        folder = Path(cls.keys_temp.name)
        for i in range(3):
            secret = folder / ('key%d.pem' % i)
            public = folder / ('public%d.pem' % i)
            subprocess.run(['openssl','genpkey','-algorithm','ed25519',
                            '-out',str(secret)], check=True, capture_output=True)
            subprocess.run(['openssl','pkey','-in',str(secret),'-pubout',
                            '-out',str(public)], check=True, capture_output=True)
            secret.chmod(0o600)
            public.chmod(0o600)
            cls.keys.append((secret,public,
                             hashlib.sha256(public.read_bytes()).hexdigest()))

    @classmethod
    def tearDownClass(cls):
        cls.keys_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.inputs = dict(
            source_url=URL, scope=SCOPE, authority_id=AUTHORITY,
            authority_public=self.keys[0][1], authority_pin=self.keys[0][2],
            notary_a_public=self.keys[1][1], notary_a_pin=self.keys[1][2],
            notary_b_public=self.keys[2][1], notary_b_pin=self.keys[2][2],
            minimum_sequence=7, expected_count=2, expected_head='1'*64,
            expected_history='2'*64, expected_witness='3'*64,
            expected_bundle='4'*64)
        self.i = 0

    def body(self, **change):
        base = {
            'schema':live.SCHEMA, 'source_url':URL,
            'authority_id':AUTHORITY, 'checkpoint_scope':SCOPE,
            'challenge_nonce':CHALLENGE, 'authority_sequence':8,
            'event_count':2, 'head_sha256':'1'*64,
            'history_sha256':'2'*64, 'latest_witness_sha256':'3'*64,
            'notary_bundle_sha256':'4'*64,
            'witness_fence_retirement_authorized':False,
        }
        base.update(change)
        return base

    def signed(self, **change):
        self.i += 1
        output = Path(self.temp.name) / ('response%d.json' % self.i)
        _sign(self.body(**change), live.SCHEMA, live.DOMAIN,
              self.keys[0][0], output)
        return output.read_bytes()

    def check(self, raw=None, **options):
        kwargs = self.inputs.copy()
        kwargs.update(options)
        return live.verify_receipt(
            self.signed() if raw is None else raw,
            challenge=CHALLENGE, **kwargs)

    def test_signed_live_head_and_external_floor_match(self):
        report = self.check()
        self.assertTrue(report['exact_stage_263w_latest_tuple_matched'])
        self.assertTrue(report['enrolled_authority_distinct_from_notaries'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertFalse(report['remote_global_latest_head_proved'])

    def test_exact_floor_is_allowed_for_read_only_latest_state(self):
        report = self.check(self.signed(authority_sequence=7))
        self.assertEqual(report['authority_sequence'],7)

    def test_old_signed_sequence_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(authority_sequence=6))

    def test_changed_external_floor_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(minimum_sequence=9)

    def test_stale_head_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(head_sha256='0'*64))

    def test_stale_full_history_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(history_sha256='0'*64))

    def test_stale_witness_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(latest_witness_sha256='0'*64))

    def test_wrong_notary_bundle_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(notary_bundle_sha256='0'*64))

    def test_replayed_old_challenge_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(challenge_nonce='b'*32))

    def test_wrong_authority_id_scope_and_url_rejected(self):
        for change in ({'authority_id':'rogue'},
                       {'checkpoint_scope':'another-scope'},
                       {'source_url':'https://other.example.org/current'}):
            with self.subTest(change=change):
                with self.assertRaises(live.LiveSourceConflict):
                    self.check(self.signed(**change))

    def test_signed_release_flag_still_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(witness_fence_retirement_authorized=True))

    def test_authority_key_cannot_equal_a_notary(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(notary_a_public=self.keys[0][1],
                       notary_a_pin=self.keys[0][2])

    def test_unpinned_and_swapped_public_keys_rejected(self):
        for change in ({'authority_pin':'f'*64},
                       {'authority_public':self.keys[1][1]},
                       {'notary_b_pin':'e'*64}):
            with self.subTest(change=list(change)):
                with self.assertRaises(ValueError):
                    self.check(**change)

    def test_bad_signature_and_extra_signed_field_rejected(self):
        signed = json.loads(self.signed())
        signed['signature_hex'] = '0'*128
        with self.assertRaises(ValueError):
            self.check(json.dumps(signed).encode())
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(extra='unexpected'))

    def test_boolean_and_overflow_sequences_rejected(self):
        for value in (True,-1,live.MAX_SEQUENCE+1,'8'):
            with self.subTest(value=value):
                with self.assertRaises(live.LiveSourceConflict):
                    self.check(self.signed(authority_sequence=value))

    def test_external_count_and_boolean_floor_rejected(self):
        with self.assertRaises(live.LiveSourceConflict):
            self.check(self.signed(event_count=3))
        with self.assertRaises(live.LiveSourceConflict):
            self.check(minimum_sequence=True)

    def test_url_must_be_exact_https_without_redirect_target(self):
        bad = ('http://independent.example.org/current',
               'https://user:pass@independent.example.org/current',
               'https://independent.example.org/current#fragment',
               'https://independent.example.org/current?alt=1',
               'https://127.0.0.1/current', 'https://localhost/current',
               'https://independent.example.org:8443/current')
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(live.LiveSourceConflict):
                    live.validate_url(url)

    def test_transport_uses_tls_post_and_no_cache(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'hello'
        opener = mock.MagicMock()
        opener.open.return_value = response
        with mock.patch.object(live.urllib.request,'build_opener',
                               return_value=opener):
            received = live.fetch_live_receipt(URL,SCOPE,CHALLENGE)
        self.assertEqual(received,b'hello')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(),'POST')
        self.assertIn(CHALLENGE,request.data.decode())
        self.assertEqual(request.get_header('Cache-control'),'no-store')

    def test_unavailable_endpoint_fails_closed(self):
        with mock.patch.object(live.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect = live.urllib.error.URLError('offline')
            with self.assertRaises(live.LiveSourceUnavailable):
                live.fetch_live_receipt(URL,SCOPE,CHALLENGE)

    def test_oversized_response_rejected(self):
        response = mock.MagicMock()
        response.__enter__.return_value=response
        response.status = 200
        response.read.return_value = b'x'*(live.MAX_RESPONSE+1)
        opener = mock.MagicMock()
        opener.open.return_value=response
        with mock.patch.object(live.urllib.request,'build_opener',
                               return_value=opener):
            with self.assertRaises(live.LiveSourceConflict):
                live.fetch_live_receipt(URL,SCOPE,CHALLENGE)

    def test_live_verifier_matches_current_generated_nonce(self):
        captured = []
        def fake_fetch(url,scope,nonce):
            captured.append((url,scope,nonce))
            return self.signed(challenge_nonce=nonce)
        report = live.verify_live(fetcher=fake_fetch, **self.inputs)
        self.assertEqual(captured[0][:2],(URL,SCOPE))
        self.assertRegex(captured[0][2],r'^[0-9a-f]{32}$')
        self.assertTrue(report['signed_fresh_client_challenge_matched'])

    def test_redacted_cli_unavailability_and_no_release(self):
        argv = [
            '--source-url',URL,
            '--source-public',str(self.keys[0][1]),
            '--source-public-pin',self.keys[0][2],
            '--authority-id',AUTHORITY,
            '--notary-a-public',str(self.keys[1][1]),
            '--notary-a-public-pin',self.keys[1][2],
            '--notary-b-public',str(self.keys[2][1]),
            '--notary-b-public-pin',self.keys[2][2],
            '--scope',SCOPE,'--external-minimum-sequence','7',
            '--expected-count','2','--expected-head','1'*64,
            '--expected-history-sha256','2'*64,
            '--expected-witness-sha256','3'*64,
            '--expected-notary-bundle-sha256','4'*64,
        ]
        with mock.patch.object(live,'fetch_live_receipt',
                               side_effect=live.LiveSourceUnavailable('offline')):
            with contextlib.redirect_stdout(out := io.StringIO()):
                result = live.main(argv)
        self.assertEqual(result,2)
        report=json.loads(out.getvalue())
        self.assertTrue(report['independent_authority_unavailable'])
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertNotIn(CHALLENGE,out.getvalue())


if __name__ == '__main__':
    unittest.main()
