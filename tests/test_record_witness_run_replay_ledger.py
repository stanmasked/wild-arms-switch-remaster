"""Stage 263L: synthetic independent observer-run replay journal tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_report_provenance as origin_fixture
from tools import audit_record_witness_run_replay_ledger as journal
from tools import audit_record_witness_composite_evidence as composite
from tools import audit_record_witness_report_provenance as origin
from tools.audit_record_witness_fence_reconciliation import _sign, _signed
from tools.audit_record_anchor_handoff import _canonical


class ReplayLedgerTests(unittest.TestCase):
    setUp = origin_fixture.ReportOriginTests.setUp
    path = origin_fixture.ReportOriginTests.path
    request = origin_fixture.ReportOriginTests.request
    stop = origin_fixture.ReportOriginTests.stop
    make_cgroup = origin_fixture.ReportOriginTests.make_cgroup
    write_controls = origin_fixture.ReportOriginTests.write_controls
    snapshot = origin_fixture.ReportOriginTests.snapshot
    signed_stop_for = origin_fixture.ReportOriginTests.signed_stop_for
    new_offer = origin_fixture.ReportOriginTests.new_offer
    make_offer_and_deposit = origin_fixture.ReportOriginTests.make_offer_and_deposit
    init_capture = origin_fixture.ReportOriginTests.init_capture
    build = origin_fixture.ReportOriginTests.build
    prepare = origin_fixture.ReportOriginTests.prepare

    @classmethod
    def setUpClass(cls):
        origin_fixture.ReportOriginTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(origin_fixture.ReportOriginTests,name))

    @classmethod
    def tearDownClass(cls):
        origin_fixture.ReportOriginTests.tearDownClass()

    def init_journal(self):
        self.prepare()
        self.journal = self.v/'independent-run-replay.sqlite'
        first = journal.initialize(self.journal)
        self.assertEqual(first['ledger_event_count'], 0)
        self.assertEqual(first['ledger_head_sha256'], journal.GENESIS)
        self.assertFalse(first['witness_fence_retirement_authorized'])
        self.head = journal.GENESIS
        self.count = 0

    def enroll(self, *, composite_raw=None, composite_pin=None,
               reports=None, signed=None, expected_count=None,
               expected_head=None):
        return journal.enroll(
            self.journal,
            self.composite_raw if composite_raw is None else composite_raw,
            self.composite_pin if composite_pin is None else composite_pin,
            self.index_raw, self.index_pin,
            self.reports if reports is None else reports,
            self.sources, self.signed if signed is None else signed,
            self.public, self.pin,
            observer_tag='independent-supervisor',
            expected_count=self.count if expected_count is None else expected_count,
            expected_head=self.head if expected_head is None else expected_head,
        )

    def second_bundle(self, seed=10):
        # Create a different valid composite AND freshly signed observer runs
        # with the same original request/stop session and source inventory.
        reports = dict(self.reports)
        item = json.loads(reports['binary'])
        item['observation_sha256'] = format(seed, '064x')
        reports['binary'] = _canonical(item)
        manifest = json.loads(self.composite_raw)
        binding = manifest['report_bindings']['binary']
        binding['observation_sha256'] = item['observation_sha256']
        binding['report_sha256'] = hashlib.sha256(reports['binary']).hexdigest()
        no_hash = dict(manifest)
        no_hash.pop('manifest_sha256')
        manifest['manifest_sha256'] = hashlib.sha256(
            composite.DOMAIN + _canonical(no_hash)).hexdigest()
        raw = _canonical(manifest)
        pin = hashlib.sha256(raw).hexdigest()
        signed = {}
        for i, kind in enumerate(origin.TOOLS):
            body = _signed(self.signed[kind], origin.CLAIM_SCHEMA,
                           origin.DOMAIN, self.pin, self.public)
            body['composite_sha256'] = pin
            body['report_sha256'] = hashlib.sha256(reports[kind]).hexdigest()
            body['run_nonce'] = format(seed*100+i, '032x')
            target = self.path('second-signed-run-'+kind+'-')
            _sign(body, origin.CLAIM_SCHEMA, origin.DOMAIN,
                  self.admins[0][1], target)
            signed[kind] = target.read_bytes()
        return raw, pin, reports, signed

    def test_initialize_and_read_only_inspection_preserve_head(self):
        self.init_journal()
        result = journal.inspect(self.journal, 0, journal.GENESIS)
        self.assertEqual(result['ledger_head_sha256'], journal.GENESIS)
        self.assertFalse(result['signed_runs_enrolled_once'])
        self.assertFalse(result['permanent_rollback_prevention_proved'])

    def test_first_eight_claim_bundle_appended_atomically(self):
        self.init_journal()
        result = self.enroll()
        self.assertEqual(result['ledger_event_count'], 1)
        self.assertTrue(result['signed_runs_enrolled_once'])
        self.assertNotEqual(result['ledger_head_sha256'], self.head)
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['tool_execution_independently_proved'])
        new = journal.inspect(self.journal, 1, result['ledger_head_sha256'])
        self.assertEqual(new['ledger_event_count'], 1)

    def test_exact_replay_rejected_even_with_updated_external_head(self):
        self.init_journal()
        first = self.enroll()
        with self.assertRaises(journal.ReplayConflict):
            self.enroll(expected_count=1,
                        expected_head=first['ledger_head_sha256'])

    def test_missing_or_stale_external_pin_rejected(self):
        self.init_journal()
        with self.assertRaises(journal.ReplayConflict):
            self.enroll(expected_head='f'*64)
        first = self.enroll()
        with self.assertRaises(journal.ReplayConflict):
            journal.inspect(self.journal, 0, self.head)
        with self.assertRaises(journal.ReplayConflict):
            self.enroll(expected_count=0, expected_head=self.head)
        self.assertEqual(
            journal.inspect(self.journal, 1,
                            first['ledger_head_sha256'])['ledger_event_count'], 1)

    def test_valid_second_distinct_bundle_extends_chain(self):
        self.init_journal()
        first = self.enroll()
        raw,pin,reports,signed = self.second_bundle()
        next_event = self.enroll(
            composite_raw=raw, composite_pin=pin, reports=reports,
            signed=signed, expected_count=1,
            expected_head=first['ledger_head_sha256'])
        self.assertEqual(next_event['ledger_event_count'], 2)
        self.assertNotEqual(next_event['ledger_head_sha256'],
                            first['ledger_head_sha256'])

    def test_reusing_old_signed_nonce_in_new_bundle_rejected(self):
        self.init_journal()
        first = self.enroll()
        raw,pin,reports,signed = self.second_bundle()
        # Sign one new claim with nonce from first event: all signatures remain
        # valid; only durable cross-bundle replay state may reject it.
        kind='binary'
        old = _signed(self.signed[kind],origin.CLAIM_SCHEMA,
                      origin.DOMAIN,self.pin,self.public)
        body = _signed(signed[kind],origin.CLAIM_SCHEMA,
                       origin.DOMAIN,self.pin,self.public)
        body['run_nonce'] = old['run_nonce']
        file = self.path('reused-nonce-')
        _sign(body,origin.CLAIM_SCHEMA,origin.DOMAIN,self.admins[0][1],file)
        signed[kind] = file.read_bytes()
        with self.assertRaises(journal.ReplayConflict):
            self.enroll(
                composite_raw=raw,composite_pin=pin,reports=reports,
                signed=signed,expected_count=1,
                expected_head=first['ledger_head_sha256'])

    def test_invalid_signature_does_not_write_to_journal(self):
        self.init_journal()
        changed = {**self.signed, 'activation': self.signed['binary']}
        with self.assertRaises((ValueError,origin.OriginConflict)):
            self.enroll(signed=changed)
        self.assertEqual(journal.inspect(
            self.journal,0,journal.GENESIS)['ledger_event_count'],0)

    def test_dropped_table_or_seal_header_detected(self):
        self.init_journal()
        with sqlite3.connect(self.journal) as con:
            con.execute('DROP TABLE observer_replay_events')
        with self.assertRaises(journal.ReplayConflict):
            journal.inspect(self.journal,0,journal.GENESIS)
        # Fresh ledger required for next test; no reset operation exists.

    def test_edited_event_hash_detected(self):
        self.init_journal()
        enrolled = self.enroll()
        with sqlite3.connect(self.journal) as con:
            con.execute("UPDATE observer_replay_events SET event_sha256=?",('a'*64,))
        with self.assertRaises(journal.ReplayConflict):
            journal.inspect(self.journal,1,enrolled['ledger_head_sha256'])

    def test_truncated_event_chain_detected_by_external_anchor(self):
        self.init_journal()
        result = self.enroll()
        with sqlite3.connect(self.journal) as con:
            con.execute('DELETE FROM observer_replay_events')
        with self.assertRaises(journal.ReplayConflict):
            journal.inspect(self.journal,1,result['ledger_head_sha256'])
        # Genesis matches local rollback, so a dishonest operator with control
        # of the external pin can still hide the truncation.
        self.assertEqual(journal.inspect(
            self.journal,0,journal.GENESIS)['ledger_event_count'],0)

    def test_overwrite_or_implicit_create_never_permitted(self):
        self.init_journal()
        with self.assertRaises(FileExistsError):
            journal.initialize(self.journal)
        self.journal.unlink()
        with self.assertRaises(FileNotFoundError):
            journal.inspect(self.journal,0,journal.GENESIS)

    def test_missing_private_ledger_or_symlink_refused(self):
        self.init_journal()
        target=self.v/'another-ledger'
        self.journal.rename(target)
        self.journal.symlink_to(target)
        with self.assertRaises(journal.ReplayConflict):
            journal.inspect(self.journal,0,journal.GENESIS)

    def test_concurrent_identical_claims_only_one_appends(self):
        self.init_journal()
        def attempt(_):
            try:
                return ('ok', self.enroll())
            except journal.ReplayConflict:
                return ('replay', None)
        with ThreadPoolExecutor(max_workers=2) as workers:
            result=list(workers.map(attempt, range(2)))
        self.assertEqual(sum(x[0]=='ok' for x in result),1)
        self.assertEqual(sum(x[0]=='replay' for x in result),1)
        head=next(x[1]['ledger_head_sha256']
                  for x in result if x[0]=='ok')
        self.assertEqual(journal.inspect(self.journal,1,head)['ledger_event_count'],1)

    def test_double_count_and_wrong_head_never_accepted(self):
        self.init_journal()
        for count,head in ((2,journal.GENESIS),(0,'e'*64),(-1,journal.GENESIS)):
            with self.subTest(count=count,head=head):
                with self.assertRaises(journal.ReplayConflict):
                    journal.inspect(self.journal,count,head)

    def test_journal_is_always_advisory_only(self):
        self.init_journal()
        output=self.enroll()
        self.assertFalse(output['independent_head_escrow_proved'])
        self.assertFalse(output['permanent_rollback_prevention_proved'])
        self.assertFalse(output['witness_fence_retired'])
        self.assertFalse(output['witness_fence_retirement_authorized'])


if __name__ == '__main__':
    unittest.main()
