"""Stage 264A deterministic ambiguous checkpoint commit recovery tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_record_witness_publication_checkpoint_cas as fixture
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_cas_reconciliation as recovery


class IndeterminateCASTests(unittest.TestCase):
    setUp = fixture.CheckpointCASTests.setUp
    expect_from = fixture.CheckpointCASTests.expect_from
    report = fixture.CheckpointCASTests.report
    advance = fixture.CheckpointCASTests.advance

    def check(self,raw=None,**change):
        raw=self.report() if raw is None else raw
        args=dict(independent_report_pin=hashlib.sha256(raw).hexdigest(),
                  scope=self.scope,**self.expected)
        args.update(change)
        return recovery.reconcile(self.path,raw,**args)

    def test_old_head_without_attempt_observed(self):
        observed=self.check()
        self.assertEqual(observed['attempt_observation'],'old_head_observed')
        self.assertEqual(observed['observed_generation'],0)
        self.assertFalse(observed['automatic_retry_authorized'])
        self.assertFalse(observed['witness_fence_retired'])

    def test_committed_but_ack_lost_is_observed(self):
        written=self.advance()
        observed=self.check()
        self.assertEqual(observed['attempt_observation'],
                         'candidate_commit_observed')
        self.assertEqual(observed['candidate_event_sha256'],
                         written['event_head_sha256'])
        self.assertEqual(observed['observed_generation'],1)
        self.assertFalse(observed['external_operator_acknowledgment_proved'])

    def test_committed_candidate_then_subsequent_valid_commit(self):
        first=self.advance()
        second_raw=self.report(previous='2'*64,proposed='4'*64,
                               count=3,seq_a=9,seq_b=13)
        self.advance(second_raw,expected=self.expect_from(first))
        observed=self.check()
        self.assertEqual(observed['attempt_observation'],'candidate_superseded')
        self.assertEqual(observed['observed_generation'],2)
        self.assertFalse(observed['externally_retained_latest_pin_proved'])

    def test_known_candidate_not_automatically_replayed(self):
        self.check()
        self.assertEqual(cas.inspect(self.path,**self.expected)['generation'],0)
        self.assertFalse(self.check()['automatic_retry_authorized'])

    def test_same_unchanged_checkpoint_under_wrong_expected_hash(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(expected_event_head='e'*64)

    def test_expected_pair_pin_mismatch(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(expected_pair_pin='e'*64)

    def test_previous_generation_mismatch(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(expected_generation=1)

    def test_previous_generation_boolean_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(expected_generation=True)

    def test_old_scope_mismatch(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(scope='different-private-scope')

    def test_report_sha256_independent_pin_mismatch(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(independent_report_pin='f'*64)

    def test_previous_report_pair_mismatch(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(self.report(previous='f'*64))

    def test_nonadvancing_signed_sequence_refused(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(self.report(seq_a=7))

    def test_nonadvancing_count_refused(self):
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(self.report(count=1))

    def test_broken_signed_safety_flag_is_refused(self):
        raw=self.report(changes={'witness_fence_retirement_authorized':True})
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(raw)

    def test_altered_pinned_report_after_commit_is_not_same_event(self):
        self.advance()
        altered=self.report(changes={'new_head_sha256':'e'*64})
        # Under Stage Z the changed report has a different pinned digest
        # even if pair/count match; it is not evidence for that commit.
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(altered)

    def test_alternative_valid_commit_at_same_generation_refused(self):
        other=self.report(proposed='9'*64)
        self.advance(other)
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check()

    def test_alternative_older_head_cannot_be_reconciled(self):
        self.advance()
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check(expected_pair_pin='f'*64)

    def test_missing_database_is_not_recreated(self):
        self.path.unlink()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check()
        self.assertFalse(self.path.exists())

    def test_mutated_chain_is_refused(self):
        self.advance()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE checkpoint_events SET report_sha256=? "
                       "WHERE generation=1",('e'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check()

    def test_changed_between_read_transactions_is_indeterminate(self):
        old_snapshot=recovery._snapshot(self.path)
        self.advance()
        new_snapshot=recovery._snapshot(self.path)
        with mock.patch.object(recovery,'_snapshot',
                               side_effect=[old_snapshot,new_snapshot]):
            with self.assertRaises(recovery.IndeterminateCASConflict):
                self.check()

    def test_readback_rejects_snapshot_of_different_scope(self):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE checkpoint_state SET scope=?',
                       ('another-operator',))
        with self.assertRaises(recovery.IndeterminateCASConflict):
            self.check()

    def test_duplicate_json_evidence_is_refused(self):
        raw=self.report()
        raw=raw[:-1]+b',"new_event_count":2}'
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(raw)

    def test_bad_full_report_schema_rejected(self):
        raw=self.report(changes={'schema':'unexpected'})
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(raw)

    def test_unreadable_or_unsafe_symlink_database_refused(self):
        link=Path(self.temp.name)/'link.db'
        link.symlink_to(self.path)
        with self.assertRaises(cas.CheckpointCASConflict):
            recovery.reconcile(link,self.report(),
                independent_report_pin=hashlib.sha256(self.report()).hexdigest(),
                scope=self.scope,**self.expected)

    def test_cli_after_lost_ack_is_redacted_read_only(self):
        self.advance()
        raw=self.report()
        file=Path(self.temp.name)/'verified-proposal.json'
        file.write_bytes(raw)
        file.chmod(0o600)
        args=[str(self.path),
              '--report-file',str(file),
              '--independent-report-pin',hashlib.sha256(raw).hexdigest(),
              '--scope',self.scope,
              '--expected-generation',str(self.expected['expected_generation']),
              '--expected-pair-pin',self.expected['expected_pair_pin'],
              '--expected-event-head',self.expected['expected_event_head']]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=recovery.main(args)
        result=json.loads(out.getvalue())
        self.assertEqual(code,0,out.getvalue())
        self.assertEqual(result['attempt_observation'],'candidate_commit_observed')
        self.assertFalse(result['automatic_retry_authorized'])
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_conflict_has_no_success_claim(self):
        raw=self.report()
        file=Path(self.temp.name)/'verified-proposal.json'
        file.write_bytes(raw)
        file.chmod(0o600)
        args=[str(self.path),'--report-file',str(file),
              '--independent-report-pin',hashlib.sha256(raw).hexdigest(),
              '--scope',self.scope,'--expected-generation','0',
              '--expected-pair-pin','f'*64,
              '--expected-event-head',self.expected['expected_event_head']]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=recovery.main(args)
        result=json.loads(out.getvalue())
        self.assertEqual(code,1)
        self.assertTrue(result['indeterminate_cas_conflict'])
        self.assertFalse(result['automatic_retry_authorized'])


if __name__=='__main__':
    unittest.main()
