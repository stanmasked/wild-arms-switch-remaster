"""Stage 263Z reference SQLite checkpoint CAS synthetic regressions."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_two_source as dual


class CheckpointCASTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'checkpoint.db'
        self.scope='private-wild-arms-publication-mirrors'
        self.pin='1'*64
        self.initial_count=1
        self.initial_a=7
        self.initial_b=11
        self.enrollment=cas.enrollment_digest(
            self.scope,self.pin,self.initial_count,self.initial_a,self.initial_b)
        self.genesis=cas.init(self.path,scope=self.scope,initial_pin=self.pin,
            count=self.initial_count,seq_a=self.initial_a,seq_b=self.initial_b,
            external_enrollment_pin=self.enrollment)
        self.expected=self.expect_from(self.genesis)

    def expect_from(self,result):
        return {
            'expected_generation':result['generation'],
            'expected_pair_pin':result['pair_sha256'],
            'expected_event_head':result['event_head_sha256'],
        }

    def report(self, *,previous=None,proposed=None,count=2,seq_a=8,seq_b=12,
               changes=None):
        item={'schema':dual.REPORT_SCHEMA}
        item.update({k:True for k in cas.TRUE_FIELDS})
        item.update({k:False for k in cas.FALSE_FIELDS})
        item.update({
            'previous_checkpoint_sha256':self.pin if previous is None else previous,
            'proposed_new_checkpoint_sha256':'2'*64 if proposed is None else proposed,
            'new_event_count':count,'new_head_sha256':'3'*64,
            'source_a_new_sequence':seq_a,'source_b_new_sequence':seq_b,
        })
        item.update(changes or {})
        return json.dumps(item,sort_keys=True).encode()

    def advance(self,raw=None,*, pin=None,expected=None):
        raw=self.report() if raw is None else raw
        return cas.advance(self.path,raw,independent_report_pin=(
            hashlib.sha256(raw).hexdigest() if pin is None else pin),
            **(self.expected if expected is None else expected))

    def test_initial_readback_matches_enrolled_pin(self):
        self.assertTrue(self.genesis['readback_matching_externally_supplied_pin'])
        self.assertEqual(self.genesis['generation'],0)
        self.assertEqual(self.genesis['pair_sha256'],self.pin)
        self.assertFalse(self.genesis['witness_fence_retired'])

    def test_first_atomic_advance_and_separate_readback(self):
        result=self.advance()
        self.assertTrue(result['atomic_sqlite_cas_and_separate_readback_verified'])
        self.assertEqual(result['generation'],1)
        self.assertEqual(result['pair_sha256'],'2'*64)
        self.assertEqual(cas.inspect(self.path,**self.expect_from(result))['event_count'],2)
        self.assertFalse(result['physical_durability_proved'])

    def test_successive_chained_generation(self):
        first=self.advance()
        raw=self.report(previous='2'*64,proposed='4'*64,
                        count=3,seq_a=9,seq_b=13)
        result=self.advance(raw,expected=self.expect_from(first))
        self.assertEqual(result['generation'],2)
        self.assertNotEqual(result['event_head_sha256'],first['event_head_sha256'])

    def test_replay_rejected_with_no_mutation(self):
        result=self.advance()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance()
        self.assertEqual(cas.inspect(self.path,**self.expect_from(result))['generation'],1)

    def test_expected_generation_mismatch(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(expected={**self.expected,'expected_generation':1})

    def test_expected_head_mismatch(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(expected={**self.expected,'expected_event_head':'a'*64})

    def test_expected_pair_mismatch(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(expected={**self.expected,'expected_pair_pin':'e'*64})

    def test_wrong_externally_pinned_report_sha(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(pin='e'*64)

    def test_signed_prior_pair_mismatch(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(previous='f'*64))

    def test_proposed_pair_equals_previous(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(proposed=self.pin))

    def test_non_advancing_publication_count(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(count=1))

    def test_non_advancing_a_sequence(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(seq_a=7))

    def test_non_advancing_b_sequence(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(seq_b=11))

    def test_forged_release_flag_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(changes={
                'witness_fence_retirement_authorized':True}))

    def test_forged_progression_flag_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(changes={
                'two_new_challenge_bound_ed25519_claims_verified':False}))

    def test_unknown_report_field_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(changes={'extra':'untrusted'}))

    def test_wrong_report_schema_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(changes={'schema':'false'}))

    def test_duplicate_top_level_report_key_rejected(self):
        raw=self.report()
        raw=raw[:-1]+b',"new_event_count":2}'
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(raw)

    def test_nonfinite_json_report_field_rejected(self):
        raw=self.report().replace(b'"new_event_count": 2',
                                  b'"new_event_count": NaN')
        self.assertIn(b'NaN',raw)
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(raw)

    def test_invalid_json_report_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(b'{malformed-json')

    def test_boolean_integer_report_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(count=True))

    def test_oversized_report_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(b' '* (cas.MAX_REPORT+1))

    def test_missing_database_never_recreated(self):
        self.path.unlink()
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)
        self.assertFalse(self.path.exists())

    def test_reinit_existing_db_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.init(self.path,scope=self.scope,initial_pin=self.pin,
                count=1,seq_a=7,seq_b=11,
                external_enrollment_pin=self.enrollment)

    def test_wrong_external_enrollment_refused_before_file_creation(self):
        newpath=Path(self.temp.name)/'new.db'
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.init(newpath,scope=self.scope,initial_pin=self.pin,
                count=1,seq_a=7,seq_b=11,
                external_enrollment_pin='f'*64)
        self.assertFalse(newpath.exists())

    def test_changed_genesis_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE checkpoint_events SET pair_sha256=? WHERE generation=0",
                       ('f'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)

    def test_truncated_chain_is_detected(self):
        result=self.advance()
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM checkpoint_events WHERE generation=1')
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expect_from(result))

    def test_modified_singleton_state_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE checkpoint_state SET pair_sha256=?',('b'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)

    def test_missing_table_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE checkpoint_events')
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)

    def test_version_seal_is_detected(self):
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA user_version=0')
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)

    def test_readback_rejects_stale_external_pins(self):
        latest=self.advance()
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)
        self.assertEqual(cas.inspect(self.path,**self.expect_from(latest))['generation'],1)

    def test_symlink_database_is_refused(self):
        link=Path(self.temp.name)/'link.db'
        link.symlink_to(self.path)
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(link,**self.expected)

    def test_file_unsafe_permissions_refused(self):
        self.path.chmod(0o644)
        with self.assertRaises(cas.CheckpointCASConflict):
            cas.inspect(self.path,**self.expected)

    def test_two_concurrent_same_expected_only_one_wins(self):
        def worker(_):
            try:
                return self.advance()['generation']
            except (cas.CheckpointCASConflict,sqlite3.DatabaseError):
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(worker,range(2)))
        self.assertEqual(results.count(1),1,results)
        self.assertEqual(results.count(None),1,results)

    def test_reject_signed_pair_without_new_signed_progress_claim(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.advance(self.report(changes={
                'new_event_count_strictly_advanced':False}))

    def test_cli_rejects_missing_external_readback_pin(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=cas.main(['inspect',str(self.path),
                             '--expected-generation','0',
                             '--expected-pair-pin',self.pin])
        self.assertEqual(status,1)
        self.assertFalse(json.loads(out.getvalue())['witness_fence_retired'])

    def test_cli_advance_commits_no_release_and_redacts_report(self):
        raw=self.report()
        file=Path(self.temp.name)/'report.json'
        file.write_bytes(raw)
        file.chmod(0o600)
        argv=['advance',str(self.path),
              '--expected-generation','0',
              '--expected-pair-pin',self.pin,
              '--expected-event-head',self.expected['expected_event_head'],
              '--report-file',str(file),
              '--independent-report-pin',hashlib.sha256(raw).hexdigest()]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=cas.main(argv)
        self.assertEqual(status,0,out.getvalue())
        report=json.loads(out.getvalue())
        self.assertEqual(report['generation'],1)
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())
        self.assertNotIn('private',out.getvalue())

    def test_explicit_rollback_of_entire_local_db_not_proved_safe(self):
        # Even an intact chain can be replaced together with old external
        # values. The operator must maintain the trusted newest head outside.
        result=self.advance()
        self.assertFalse(result['rollback_protection_without_external_pins_proved'])
        self.assertFalse(result['independent_operator_or_host_proved'])


if __name__ == '__main__':
    unittest.main()
