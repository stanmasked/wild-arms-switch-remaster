"""Stage 264B synthetic keeper reconnect + dual fresh Ed25519 verification."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

from tests import test_record_witness_publication_two_source as prior_fixture
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_live_source as live
from tools import audit_record_witness_publication_reconnect_crosscheck as check
from tools import audit_record_witness_publication_cas_reconciliation as recovery
from tools import audit_record_witness_publication_two_source as dual


class ReconnectCrosscheckTests(unittest.TestCase):
    setUpClass = prior_fixture.DualAuthorityTests.__dict__['setUpClass']
    tearDownClass = prior_fixture.DualAuthorityTests.__dict__['tearDownClass']
    sign = prior_fixture.DualAuthorityTests.sign
    compute_pin = prior_fixture.DualAuthorityTests.compute_pin

    def setUp(self):
        prior_fixture.DualAuthorityTests.setUp(self)
        self.db=Path(self.temp.name)/'keeper.db'
        self.expected={key:self.old[key]
            for key in ('count','head','history','witness','bundle')}
        enroll=cas.enrollment_digest(self.scope,self.pin,
            self.old['count'],self.old['sequence_a'],self.old['sequence_b'])
        self.initial=cas.init(self.db,scope=self.scope,initial_pin=self.pin,
            count=self.old['count'],seq_a=self.old['sequence_a'],
            seq_b=self.old['sequence_b'],external_enrollment_pin=enroll)
        self.nonces=('c'*32,'d'*32)
        self.calls=[]

    def fetch(self,url,scope,nonce):
        self.calls.append((url,scope,nonce))
        if url==self.source_a['source_url']:
            return self.sign(self.source_a,0,self.expected,
                             challenge=nonce,sequence=7)
        if url==self.source_b['source_url']:
            return self.sign(self.source_b,1,self.expected,
                             challenge=nonce,sequence=11)
        raise AssertionError('unexpected source URL')

    def arguments(self):
        return dict(
            archived_nonce_a=self.old['challenge_a'],
            archived_nonce_b=self.old['challenge_b'],
            source_a=self.source_a,source_b=self.source_b,
            notaries=self.notaries,scope=self.scope,
            expected=self.expected,
            expected_generation=self.initial['generation'],
            expected_pair_pin=self.initial['pair_sha256'],
            expected_event_head=self.initial['event_head_sha256'],
            fetcher=self.fetch,challenges=self.nonces,
        )

    def run_check(self,**changed):
        args=self.arguments()
        args.update(changed)
        return check.recheck(self.db,self.old_raw_a,self.old_raw_b,**args)

    def _advanced_keeper(self):
        report={'schema':dual.REPORT_SCHEMA}
        report.update({key:True for key in cas.TRUE_FIELDS})
        report.update({key:False for key in cas.FALSE_FIELDS})
        report.update({
            'previous_checkpoint_sha256':self.pin,
            'proposed_new_checkpoint_sha256':'e'*64,
            'new_event_count':2,'new_head_sha256':'f'*64,
            'source_a_new_sequence':8,'source_b_new_sequence':12,
        })
        raw=json.dumps(report,sort_keys=True).encode()
        return cas.advance(self.db,raw,
            independent_report_pin=hashlib.sha256(raw).hexdigest(),
            expected_generation=0,expected_pair_pin=self.pin,
            expected_event_head=self.initial['event_head_sha256'])

    def test_both_fresh_signatures_and_keeper_match(self):
        report=self.run_check()
        self.assertTrue(report['fresh_online_sources_agree_with_pinned_stage_263w_tuple'])
        self.assertEqual(report['fresh_source_a_sequence'],7)
        self.assertEqual(report['fresh_source_b_sequence'],11)
        self.assertEqual(len(self.calls),2)
        self.assertFalse(report['automatic_cas_retry_authorized'])
        self.assertFalse(report['witness_fence_retirement_authorized'])

    def test_archived_signed_envelopes_not_required_as_fresh_bytes(self):
        self.assertTrue(self.run_check()['two_new_distinct_challenge_ed25519_responses_valid'])
        self.assertFalse(self.run_check()['fresh_signed_envelopes_equal_archived_envelopes_required'])

    def test_source_sequence_can_advance_without_new_publication_count(self):
        def advanced(url,scope,nonce):
            index=0 if url==self.source_a['source_url'] else 1
            return self.sign(self.source_a if index==0 else self.source_b,
                 index,self.expected,challenge=nonce,
                 sequence=8 if index==0 else 12)
        observed=self.run_check(fetcher=advanced)
        self.assertEqual((observed['fresh_source_a_sequence'],
                          observed['fresh_source_b_sequence']),(8,12))

    def test_wrong_external_pair_pin_rejected(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(expected_pair_pin='e'*64)

    def test_wrong_external_event_head_rejected(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(expected_event_head='e'*64)

    def test_wrong_generation_rejected(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(expected_generation=1)

    def test_boolean_expected_generation_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.run_check(expected_generation=True)

    def test_wrong_expected_count_rejected_before_network(self):
        changed=self.expected.copy()
        changed['count']=2
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(expected=changed)
        self.assertEqual(self.calls,[])

    def test_wrong_expected_history_rejected(self):
        changed=self.expected.copy()
        changed['history']='f'*64
        with self.assertRaises(live.LiveSourceConflict):
            self.run_check(expected=changed)

    def test_bad_enrollment_scope_rejected(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(scope='different-operator-scope')

    def test_same_dns_host_for_both_sources_rejected(self):
        source=self.source_b.copy()
        source['source_url']=self.source_a['source_url']
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(source_b=source)

    def test_same_authority_id_rejected(self):
        source=self.source_b.copy()
        source['authority_id']=self.source_a['authority_id']
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(source_b=source)

    def test_same_ed25519_key_rejected(self):
        source=self.source_b.copy()
        source['authority_public']=self.source_a['authority_public']
        source['authority_pin']=self.source_a['authority_pin']
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(source_b=source)

    def test_authority_key_equal_notary_refused(self):
        notaries=self.notaries.copy()
        notaries['notary_a_public']=self.source_a['authority_public']
        notaries['notary_a_pin']=self.source_a['authority_pin']
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(notaries=notaries)

    def test_wrong_public_pem_pin_rejected(self):
        source=self.source_a.copy()
        source['authority_pin']='f'*64
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(source_a=source)

    def test_invalid_archived_challenge_refused(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(archived_nonce_a='x'*32)

    def test_reuse_of_archived_nonce_refused(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(challenges=('c'*32,self.old['challenge_b']))

    def test_duplicate_fresh_nonce_refused(self):
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(challenges=('c'*32,'c'*32))

    def test_fresh_source_b_wrong_head_rejected(self):
        def bad(url,scope,nonce):
            if url==self.source_b['source_url']:
                return self.sign(self.source_b,1,self.expected,
                    challenge=nonce,sequence=11,head_sha256='f'*64)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.run_check(fetcher=bad)

    def test_fresh_source_a_wrong_history_rejected(self):
        def bad(url,scope,nonce):
            if url==self.source_a['source_url']:
                return self.sign(self.source_a,0,self.expected,
                    challenge=nonce,sequence=7,history_sha256='e'*64)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.run_check(fetcher=bad)

    def test_fresh_source_rollback_rejected(self):
        def bad(url,scope,nonce):
            if url==self.source_a['source_url']:
                return self.sign(self.source_a,0,self.expected,
                    challenge=nonce,sequence=6)
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceConflict):
            self.run_check(fetcher=bad)

    def test_missing_source_never_forms_partial_quorum(self):
        def unavailable(url,scope,nonce):
            if url==self.source_b['source_url']:
                raise live.LiveSourceUnavailable('offline')
            return self.fetch(url,scope,nonce)
        with self.assertRaises(live.LiveSourceUnavailable):
            self.run_check(fetcher=unavailable)

    def test_fresh_replay_of_archived_signed_reply_rejected(self):
        def replay(url,scope,nonce):
            return self.old_raw_a if url==self.source_a['source_url'] else self.old_raw_b
        with self.assertRaises(live.LiveSourceConflict):
            self.run_check(fetcher=replay)

    def test_keeper_advanced_after_independent_pin_rejected(self):
        self._advanced_keeper()
        with self.assertRaises(check.ReconnectConflict):
            self.run_check()

    def test_keeper_tampered_event_chain_rejected(self):
        with sqlite3.connect(self.db) as con:
            con.execute('UPDATE checkpoint_events SET pair_sha256=? WHERE generation=0',
                        ('f'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            self.run_check()

    def test_keeper_mutated_during_network_crosscheck_rejected(self):
        fired=[False]
        def raced(url,scope,nonce):
            if not fired[0]:
                fired[0]=True
                self._advanced_keeper()
            return self.fetch(url,scope,nonce)
        with self.assertRaises(check.ReconnectConflict):
            self.run_check(fetcher=raced)

    def test_missing_keeper_never_recreated(self):
        self.db.unlink()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.run_check()
        self.assertFalse(self.db.exists())

    def test_result_explicitly_disclaims_external_independence(self):
        result=self.run_check()
        self.assertFalse(result['physical_authority_independence_proved'])
        self.assertFalse(result['external_monotonic_pin_storage_proved'])
        self.assertFalse(result['remote_global_latest_head_proved'])
        self.assertFalse(result['native_switch_game_build_verified'])

    def test_cli_unavailable_source_redacted_and_no_release(self):
        from tempfile import TemporaryDirectory
        args=[str(self.db),'--scope',self.scope,
            '--expected-generation','0',
            '--expected-pair-pin',self.pin,
            '--expected-event-head',self.initial['event_head_sha256'],
            '--expected-count',str(self.expected['count'])]
        for key in ('head','history','witness','bundle'):
            args.extend(['--expected-'+key+'-sha256',self.expected[key]])
        for role,source,raw,nonce in (
            ('a',self.source_a,self.old_raw_a,self.old['challenge_a']),
            ('b',self.source_b,self.old_raw_b,self.old['challenge_b'])):
            saved=Path(self.temp.name)/('archive-'+role+'.json')
            saved.write_bytes(raw)
            saved.chmod(0o600)
            for part,value in (
                    ('url',source['source_url']),
                    ('id',source['authority_id']),
                    ('public',str(source['authority_public'])),
                    ('pin',source['authority_pin'])):
                args.extend(['--source-'+role+'-'+part,value])
            args.extend(['--archived-'+role+'-signed',str(saved),
                         '--archived-'+role+'-nonce',nonce,
                         '--notary-'+role+'-public',
                         str(self.notaries['notary_'+role+'_public']),
                         '--notary-'+role+'-pin',
                         self.notaries['notary_'+role+'_pin']])
        with mock.patch.object(check.secrets,'token_hex',
                side_effect=['c'*32,'d'*32]):
            with mock.patch.object(live,'fetch_live_receipt',
                    side_effect=live.LiveSourceUnavailable('offline')):
                with contextlib.redirect_stdout(out:=io.StringIO()):
                    status=check.main(args)
        self.assertEqual(status,2,out.getvalue())
        obj=json.loads(out.getvalue())
        self.assertTrue(obj['source_unavailable'])
        self.assertFalse(obj['witness_fence_retired'])
        self.assertFalse(obj['automatic_cas_retry_authorized'])
        self.assertNotIn('private',out.getvalue())


if __name__ == '__main__':
    unittest.main()
