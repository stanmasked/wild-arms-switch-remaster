"""Stage 263K: pinned code origin and independent observer signature tests."""
import copy
import hashlib
import json
import unittest

from tests import test_record_witness_composite_evidence as fixture
from tools.audit_record_anchor_handoff import _canonical
from tools.audit_record_witness_fence_reconciliation import _sign
from tools import audit_record_witness_composite_evidence as composite
from tools import audit_record_witness_report_provenance as provenance


class ReportOriginTests(unittest.TestCase):
    setUp = fixture.CompositeEvidenceTests.setUp
    request = fixture.CompositeEvidenceTests.request
    path = fixture.CompositeEvidenceTests.path
    stop = fixture.CompositeEvidenceTests.stop
    make_cgroup = fixture.CompositeEvidenceTests.make_cgroup
    write_controls = fixture.CompositeEvidenceTests.write_controls
    snapshot = fixture.CompositeEvidenceTests.snapshot
    signed_stop_for = fixture.CompositeEvidenceTests.signed_stop_for
    new_offer = fixture.CompositeEvidenceTests.new_offer
    make_offer_and_deposit = fixture.CompositeEvidenceTests.make_offer_and_deposit
    init_capture = fixture.CompositeEvidenceTests.init_capture
    build = fixture.CompositeEvidenceTests.build

    @classmethod
    def setUpClass(cls):
        fixture.CompositeEvidenceTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.CompositeEvidenceTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.CompositeEvidenceTests.tearDownClass()

    def prepare(self):
        self.init_capture()
        self.composite_raw = _canonical(self.build())
        self.composite_pin = hashlib.sha256(self.composite_raw).hexdigest()
        self.sources = {kind:(b'# synthetic pinned tool '+kind.encode()+b'\n')
                        for kind in provenance.TOOLS}
        self.index_raw = _canonical({
            'schema': provenance.INDEX_SCHEMA,
            'tools': {
                kind: {
                    'path':provenance.TOOLS[kind],
                    'sha256':hashlib.sha256(self.sources[kind]).hexdigest(),
                }
                for kind in provenance.TOOLS
            },
        })
        self.index_pin = hashlib.sha256(self.index_raw).hexdigest()
        self.signed = {}
        session = json.loads(self.composite_raw)['session']
        for index, kind in enumerate(provenance.TOOLS):
            body = {
                'schema':provenance.CLAIM_SCHEMA,
                'observer_tag':'independent-supervisor',
                'report_kind':kind,
                'report_schema':composite.SPECS[kind][0],
                'report_sha256':hashlib.sha256(self.reports[kind]).hexdigest(),
                'source_path':provenance.TOOLS[kind],
                'source_sha256':hashlib.sha256(self.sources[kind]).hexdigest(),
                'source_index_sha256':self.index_pin,
                'composite_sha256':self.composite_pin,
                'original_request_sha256':session['original_request_sha256'],
                'signed_stop_sha256':session['signed_supervisor_stop_sha256'],
                'stop_session_nonce':session['stop_session_nonce'],
                'run_nonce':format(index+1,'032x'),
            }
            output = self.path('signed-origin-'+kind+'-')
            _sign(body,provenance.CLAIM_SCHEMA,provenance.DOMAIN,
                  self.admins[0][1],output)
            self.signed[kind] = output.read_bytes()

    def check(self, *, composite_raw=None, composite_pin=None, index_raw=None,
              index_pin=None, sources=None, reports=None, signed=None,
              observer_key=None, observer_pin=None):
        return provenance.verify(
            self.composite_raw if composite_raw is None else composite_raw,
            self.composite_pin if composite_pin is None else composite_pin,
            self.index_raw if index_raw is None else index_raw,
            self.index_pin if index_pin is None else index_pin,
            self.reports if reports is None else reports,
            self.sources if sources is None else sources,
            self.signed if signed is None else signed,
            self.public if observer_key is None else observer_key,
            self.pin if observer_pin is None else observer_pin,
            observer_tag='independent-supervisor')

    def test_eight_verified_signatures_are_advisory_only(self):
        self.prepare()
        report=self.check()
        self.assertTrue(report['all_eight_observer_ed25519_claims_valid'])
        self.assertTrue(report['exact_report_bytes_and_tool_source_pinned'])
        self.assertFalse(report['tool_execution_independently_proved'])
        self.assertFalse(report['cross_run_replay_registry_enforced'])
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertFalse(report['witness_fence_retired'])

    def test_missing_or_extra_signed_run_refused(self):
        self.prepare()
        with self.assertRaises(provenance.OriginConflict):
            self.check(signed={k:v for k,v in self.signed.items()
                               if k!='activation'})
        with self.assertRaises(provenance.OriginConflict):
            self.check(signed={**self.signed,'unexpected':b'bad'})

    def test_report_bytes_modified_after_signing_refused(self):
        self.prepare()
        changed = {**self.reports,'activation':
                   self.reports['activation']+b' '}
        with self.assertRaises(provenance.OriginConflict):
            self.check(reports=changed)

    def test_tool_source_swap_refused(self):
        self.prepare()
        changed = {**self.sources,'binary':b'altered binary tool\n'}
        with self.assertRaises(provenance.OriginConflict):
            self.check(sources=changed)

    def test_wrong_independent_source_index_pin_refused(self):
        self.prepare()
        with self.assertRaises(provenance.OriginConflict):
            self.check(index_pin='f'*64)

    def test_source_index_unexpected_path_refused(self):
        self.prepare()
        index=json.loads(self.index_raw)
        index['tools']['binary']['path']='tools/another-tool.py'
        raw=_canonical(index)
        with self.assertRaises(provenance.OriginConflict):
            self.check(index_raw=raw,
                       index_pin=hashlib.sha256(raw).hexdigest())

    def test_source_index_duplicate_or_missing_tool_refused(self):
        self.prepare()
        index=json.loads(self.index_raw)
        del index['tools']['launchers']
        raw=_canonical(index)
        with self.assertRaises(provenance.OriginConflict):
            self.check(index_raw=raw,index_pin=hashlib.sha256(raw).hexdigest())

    def test_modified_composite_pin_refused(self):
        self.prepare()
        with self.assertRaises(provenance.OriginConflict):
            self.check(composite_pin='f'*64)

    def test_composite_content_change_refused(self):
        self.prepare()
        with self.assertRaises(provenance.OriginConflict):
            self.check(composite_raw=self.composite_raw+b' ')

    def test_signed_run_wrong_observer_public_key_pin(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.check(observer_pin='e'*64)

    def test_signed_run_envelope_rewritten_refused(self):
        self.prepare()
        changed = {**self.signed,
                   'preflight':self.signed['preflight'].replace(
                       b'independent-supervisor',b'unknown-supervisor')}
        with self.assertRaises(ValueError):
            self.check(signed=changed)

    def test_signed_reports_swapped_refused(self):
        self.prepare()
        changed=dict(self.signed)
        changed['cgroup'],changed['preflight']=(
            changed['preflight'],changed['cgroup'])
        with self.assertRaises(provenance.OriginConflict):
            self.check(signed=changed)

    def test_duplicate_run_nonce_detected(self):
        self.prepare()
        # Explicitly re-sign the second claim with the first claim's nonce.
        from tools.audit_record_witness_fence_reconciliation import _signed
        one = _signed(self.signed['binary'],provenance.CLAIM_SCHEMA,
                      provenance.DOMAIN,self.pin,self.public)
        two = _signed(self.signed['interpreted'],provenance.CLAIM_SCHEMA,
                      provenance.DOMAIN,self.pin,self.public)
        two['run_nonce']=one['run_nonce']
        target=self.path('duplicate-origin-nonce-')
        _sign(two,provenance.CLAIM_SCHEMA,provenance.DOMAIN,
              self.admins[0][1],target)
        with self.assertRaises(provenance.OriginConflict):
            self.check(signed={**self.signed,
                               'interpreted':target.read_bytes()})

    def test_valid_signed_claim_bound_to_old_session_refused(self):
        self.prepare()
        from tools.audit_record_witness_fence_reconciliation import _signed
        body=_signed(self.signed['activation'],provenance.CLAIM_SCHEMA,
                     provenance.DOMAIN,self.pin,self.public)
        body['stop_session_nonce']='e'*32
        target=self.path('old-session-origin-')
        _sign(body,provenance.CLAIM_SCHEMA,provenance.DOMAIN,
              self.admins[0][1],target)
        with self.assertRaises(provenance.OriginConflict):
            self.check(signed={**self.signed,
                               'activation':target.read_bytes()})

    def test_source_code_self_enrollment_cannot_rewrite_pin(self):
        self.prepare()
        index=json.loads(self.index_raw)
        index['tools']['quarantine']['sha256']='b'*64
        changed=_canonical(index)
        with self.assertRaises(provenance.OriginConflict):
            self.check(index_raw=changed)

    def test_incomplete_composite_safety_refused(self):
        self.prepare()
        body=json.loads(self.composite_raw)
        del body['safety']['witness_fence_retired']
        bad=_canonical(body)
        with self.assertRaises(provenance.OriginConflict):
            self.check(composite_raw=bad,
                       composite_pin=hashlib.sha256(bad).hexdigest())

    def test_false_global_release_claim_refused(self):
        self.prepare()
        body=json.loads(self.composite_raw)
        body['safety']['witness_fence_retirement_authorized']=True
        bad=_canonical(body)
        with self.assertRaises(provenance.OriginConflict):
            self.check(composite_raw=bad,
                       composite_pin=hashlib.sha256(bad).hexdigest())


if __name__ == '__main__':
    unittest.main()
