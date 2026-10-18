"""Stage 264D co-endorsed highwater transition regressions, synthetic only."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest

from tests import test_record_witness_publication_dual_operator_highwater as fixture
from tools import audit_record_witness_publication_highwater_lineage as lineage
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_witness_fence_reconciliation import _sign


class HighwaterLineageTests(unittest.TestCase):
    setUpClass=fixture.DualOperatorHighwaterTests.__dict__['setUpClass']
    tearDownClass=fixture.DualOperatorHighwaterTests.__dict__['tearDownClass']
    sign=fixture.DualOperatorHighwaterTests.sign
    compute_pin=fixture.DualOperatorHighwaterTests.compute_pin
    fetch=fixture.DualOperatorHighwaterTests.fetch
    _advanced_keeper=fixture.DualOperatorHighwaterTests._advanced_keeper
    certificate=fixture.DualOperatorHighwaterTests.certificate

    def setUp(self):
        fixture.DualOperatorHighwaterTests.setUp(self)
        self.old_a,self.old_b=self.cert_a,self.cert_b
        self.latest=self._advanced_keeper()
        self.floors=(19,33)
        self.new_a=self.certificate(0,snapshot=self.latest)
        self.new_b=self.certificate(1,snapshot=self.latest)
        self.previous='e'*64
        self.counter=0
        self.pinned={
            'old_a':hashlib.sha256(self.old_a).hexdigest(),
            'old_b':hashlib.sha256(self.old_b).hexdigest(),
            'new_a':hashlib.sha256(self.new_a).hexdigest(),
            'new_b':hashlib.sha256(self.new_b).hexdigest(),
        }
        self.signed_a=self.endorse(0)
        self.signed_b=self.endorse(1)
        self.pinned['endorsement_a']=hashlib.sha256(self.signed_a).hexdigest()
        self.pinned['endorsement_b']=hashlib.sha256(self.signed_b).hexdigest()

    def body(self,idx,change=None):
        x={
            'schema':lineage.SCHEMA,
            'operator_id':'offhost-highwater-'+('a' if idx==0 else 'b'),
            'checkpoint_scope':self.scope,
            'previous_transition_bundle_sha256':self.previous,
            'old_operator_a_certificate_sha256':self.pinned['old_a'],
            'old_operator_b_certificate_sha256':self.pinned['old_b'],
            'new_operator_a_certificate_sha256':self.pinned['new_a'],
            'new_operator_b_certificate_sha256':self.pinned['new_b'],
            'old_generation':self.initial['generation'],
            'old_pair_sha256':self.initial['pair_sha256'],
            'old_event_head_sha256':self.initial['event_head_sha256'],
            'new_generation':self.latest['generation'],
            'new_pair_sha256':self.latest['pair_sha256'],
            'new_event_head_sha256':self.latest['event_head_sha256'],
            'witness_fence_retirement_authorized':False,
        }
        x.update(change or {})
        return x

    def endorse(self,idx,change=None):
        self.counter+=1
        path=Path(self.temp.name)/('lineage-%d.json'%self.counter)
        _sign(self.body(idx,change),lineage.SCHEMA,lineage.DOMAIN,
              self.observers[idx][0],path)
        return path.read_bytes()

    def check(self,**change):
        args=dict(
            scope=self.scope,
            operator_a_id='offhost-highwater-a',
            operator_b_id='offhost-highwater-b',
            operator_a_public=self.observers[0][1],
            operator_a_pin=self.observers[0][2],
            operator_b_public=self.observers[1][1],
            operator_b_pin=self.observers[1][2],
            externally_pinned=dict(self.pinned),
            previous_transition_bundle_sha256=self.previous,
            expected_generation=self.latest['generation'],
            expected_pair_pin=self.latest['pair_sha256'],
            expected_event_head=self.latest['event_head_sha256'])
        args.update(change)
        return lineage.verify(self.db,self.old_a,self.old_b,
            self.new_a,self.new_b,self.signed_a,self.signed_b,**args)

    def test_paired_signed_transition_verified(self):
        o=self.check()
        self.assertTrue(o['two_signed_paired_highwaters_strictly_advanced'])
        self.assertTrue(o['both_operator_endorsements_bind_same_old_and_new_certificates'])
        self.assertEqual(o['old_generation'],0)
        self.assertEqual(o['new_generation'],1)
        self.assertFalse(o['witness_fence_retired'])

    def test_output_pin_stably_reproducible(self):
        first=self.check()
        second=self.check()
        self.assertEqual(first['proposed_successor_transition_bundle_sha256'],
                         second['proposed_successor_transition_bundle_sha256'])
        self.assertFalse(first['externally_persisted_successor_bundle_proved'])

    def test_successor_external_pin_accepted_when_exact(self):
        result=self.check()
        self.assertTrue(self.check(expected_successor_bundle_sha256=
            result['proposed_successor_transition_bundle_sha256'])[
                'new_checkpoint_matches_independently_supplied_current_head'])

    def test_different_successor_external_pin_rejected(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(expected_successor_bundle_sha256='d'*64)

    def test_previous_bundle_link_tamper_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(previous_transition_bundle_sha256='a'*64)

    def test_null_previous_bundle_is_not_a_pin(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(previous_transition_bundle_sha256=None)

    def test_wrong_current_generation_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(expected_generation=0)

    def test_wrong_current_pair_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(expected_pair_pin='d'*64)

    def test_wrong_current_chain_head_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(expected_event_head='d'*64)

    def test_duplicate_operator_id_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(operator_b_id='offhost-highwater-a')

    def test_duplicate_operator_ed25519_key_refused(self):
        with self.assertRaises(lineage.LineageConflict):
            self.check(operator_b_public=self.observers[0][1],
                       operator_b_pin=self.observers[0][2])

    def test_missing_cert_pin_refused(self):
        bad=dict(self.pinned)
        bad.pop('old_b')
        with self.assertRaises(lineage.LineageConflict):
            self.check(externally_pinned=bad)

    def test_wrong_old_operator_cert_hash_refused(self):
        bad=dict(self.pinned)
        bad['old_a']='f'*64
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(externally_pinned=bad)

    def test_wrong_new_operator_cert_hash_refused(self):
        bad=dict(self.pinned)
        bad['new_b']='f'*64
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(externally_pinned=bad)

    def test_wrong_endorsement_a_envelope_hash_refused(self):
        bad=dict(self.pinned)
        bad['endorsement_a']='f'*64
        with self.assertRaises(lineage.LineageConflict):
            self.check(externally_pinned=bad)

    def test_wrong_endorsement_b_envelope_hash_refused(self):
        bad=dict(self.pinned)
        bad['endorsement_b']='f'*64
        with self.assertRaises(lineage.LineageConflict):
            self.check(externally_pinned=bad)

    def test_nonprogressing_operator_seal_refused(self):
        original=self.new_a
        new=self.certificate(0,snapshot=self.latest,
                             change={'seal_sequence':18})
        self.new_a=new
        bad=dict(self.pinned,new_a=hashlib.sha256(new).hexdigest())
        try:
            with self.assertRaises(cas.CheckpointCASConflict):
                self.check(externally_pinned=bad)
        finally:
            self.new_a=original

    def test_nonadvancing_new_source_sequence_refused(self):
        old=self.new_b
        new=self.certificate(1,snapshot=self.latest,
                             change={'source_b_sequence':11})
        self.new_b=new
        bad=dict(self.pinned,new_b=hashlib.sha256(new).hexdigest())
        try:
            with self.assertRaises(lineage.LineageConflict):
                self.check(externally_pinned=bad)
        finally:
            self.new_b=old

    def test_conflicting_new_operator_highwaters_refused(self):
        old=self.new_b
        new=self.certificate(1,snapshot=self.latest,
                             change={'event_count':3})
        self.new_b=new
        bad=dict(self.pinned,new_b=hashlib.sha256(new).hexdigest())
        try:
            with self.assertRaises(lineage.LineageConflict):
                self.check(externally_pinned=bad)
        finally:
            self.new_b=old

    def test_changed_endorsement_old_certificate_digest_refused(self):
        raw=self.endorse(0,{'old_operator_a_certificate_sha256':'f'*64})
        self.signed_a=raw
        self.pinned['endorsement_a']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(lineage.LineageConflict):
            self.check()

    def test_changed_endorsement_new_certificate_digest_refused(self):
        raw=self.endorse(1,{'new_operator_b_certificate_sha256':'f'*64})
        self.signed_b=raw
        self.pinned['endorsement_b']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(lineage.LineageConflict):
            self.check()

    def test_endorsement_scope_conflict_refused(self):
        raw=self.endorse(1,{'checkpoint_scope':'another-scope'})
        self.signed_b=raw
        self.pinned['endorsement_b']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(lineage.LineageConflict):
            self.check()

    def test_replay_of_operator_a_endorsement_as_b_refused(self):
        self.signed_b=self.signed_a
        self.pinned['endorsement_b']=self.pinned['endorsement_a']
        with self.assertRaises(ValueError):
            self.check()

    def test_forged_release_authorization_refused(self):
        raw=self.endorse(0,{'witness_fence_retirement_authorized':True})
        self.signed_a=raw
        self.pinned['endorsement_a']=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(lineage.LineageConflict):
            self.check()

    def test_corrupt_keeper_chain_refused(self):
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE checkpoint_events SET pair_sha256=? WHERE generation=1',
                        ('f'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check()

    def test_missing_keeper_not_recreated(self):
        self.db.unlink()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check()
        self.assertFalse(self.db.exists())

    def test_alternate_valid_pair_rejected_by_pinned_successor(self):
        old_bundle=self.check()['proposed_successor_transition_bundle_sha256']
        # Two already-valid successor certificates can have different valid
        # observer seal counters. Without a *retained external successor pin*
        # neither the signatures nor old bundle hash alone proves uniqueness.
        self.new_b=self.certificate(1,snapshot=self.latest,
                                    change={'seal_sequence':34})
        self.pinned['new_b']=hashlib.sha256(self.new_b).hexdigest()
        self.signed_a=self.endorse(0)
        self.signed_b=self.endorse(1)
        self.pinned['endorsement_a']=hashlib.sha256(self.signed_a).hexdigest()
        self.pinned['endorsement_b']=hashlib.sha256(self.signed_b).hexdigest()
        alternate=self.check()
        self.assertNotEqual(old_bundle,
                            alternate['proposed_successor_transition_bundle_sha256'])
        with self.assertRaises(lineage.LineageConflict):
            self.check(expected_successor_bundle_sha256=old_bundle)

    def test_disclaimers_do_not_assert_fork_exclusion(self):
        r=self.check()
        self.assertFalse(r['unique_successor_or_fork_absence_proved'])
        self.assertFalse(r['real_external_operator_independence_proved'])
        self.assertFalse(r['globally_latest_publication_proved'])
        self.assertFalse(r['automatic_cas_retry_authorized'])

    def test_cli_missing_certificate_reports_failure_without_release(self):
        files={}
        for key,raw in (('old_a',self.old_a),('old_b',self.old_b),
                        ('new_a',self.new_a),('new_b',self.new_b),
                        ('endorsement_a',self.signed_a),
                        ('endorsement_b',self.signed_b)):
            path=Path(self.temp.name)/('submitted-'+key+'.json')
            path.write_bytes(raw)
            path.chmod(0o600)
            files[key]=path
        args=[str(self.db),'--scope',self.scope,
              '--operator-a-id','offhost-highwater-a',
              '--operator-b-id','offhost-highwater-b',
              '--previous-transition-bundle-sha256',self.previous,
              '--expected-generation','1',
              '--expected-pair-pin',self.latest['pair_sha256'],
              '--expected-event-head',self.latest['event_head_sha256']]
        for name,idx in (('a',0),('b',1)):
            args.extend(['--operator-'+name+'-public',
                         str(self.observers[idx][1]),
                         '--operator-'+name+'-pin',
                         self.observers[idx][2]])
            for moment in ('old','new'):
                item=moment+'_'+name
                args.extend(['--'+moment+'-'+name+'-certificate',str(files[item]),
                             '--'+moment+'-'+name+'-sha256',self.pinned[item]])
            item='endorsement_'+name
            args.extend(['--endorsement-'+name,str(files[item]),
                         '--endorsement-'+name+'-sha256','f'*64])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=lineage.main(args)
        obj=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(obj['highwater_transition_conflict'])
        self.assertFalse(obj['witness_fence_retired'])
        self.assertFalse(obj['automatic_cas_retry_authorized'])
        self.assertNotIn('signature_hex',out.getvalue())
        # Also exercise the missing-input-file path after file opening moved
        # into the fail-closed CLI exception handler.
        files['old_a'].unlink()
        with contextlib.redirect_stdout(missing:=io.StringIO()):
            missing_status=lineage.main(args)
        missing_result=json.loads(missing.getvalue())
        self.assertEqual(missing_status,1)
        self.assertTrue(missing_result['highwater_transition_conflict'])
        self.assertFalse(missing_result['witness_fence_retired'])
        self.assertFalse(missing_result['automatic_cas_retry_authorized'])


if __name__=='__main__':
    unittest.main()
