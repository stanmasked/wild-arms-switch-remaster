"""Stage 264C two independently enrolled high-watermark signers, synthetic."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_dual_operator_highwater as high
from tools import audit_record_witness_publication_live_source as live
from tools import audit_record_witness_publication_two_source as dual
from tools.audit_record_witness_fence_reconciliation import _sign
from tests import test_record_witness_publication_reconnect_crosscheck as base


class DualOperatorHighwaterTests(unittest.TestCase):
    setUpClass=base.ReconnectCrosscheckTests.__dict__['setUpClass']
    tearDownClass=base.ReconnectCrosscheckTests.__dict__['tearDownClass']
    sign=base.ReconnectCrosscheckTests.sign
    compute_pin=base.ReconnectCrosscheckTests.compute_pin
    fetch=base.ReconnectCrosscheckTests.fetch
    _advanced_keeper=base.ReconnectCrosscheckTests._advanced_keeper

    def setUp(self):
        base.ReconnectCrosscheckTests.setUp(self)
        self.observers=[]
        for i in range(2):
            private=Path(self.temp.name)/('seal-private-%d.pem'%i)
            public=Path(self.temp.name)/('seal-public-%d.pem'%i)
            subprocess.run(['openssl','genpkey','-algorithm','ed25519',
                            '-out',str(private)],capture_output=True,check=True)
            subprocess.run(['openssl','pkey','-in',str(private),'-pubout',
                            '-out',str(public)],capture_output=True,check=True)
            private.chmod(0o600)
            public.chmod(0o600)
            self.observers.append((private,public,
                         hashlib.sha256(public.read_bytes()).hexdigest()))
        self.serial=0
        self.floors=(18,32)
        self.cert_a=self.certificate(0)
        self.cert_b=self.certificate(1)
        self.hash_a=hashlib.sha256(self.cert_a).hexdigest()
        self.hash_b=hashlib.sha256(self.cert_b).hexdigest()

    def identities(self):
        return (
            (self.source_a['authority_public'],self.source_a['authority_pin']),
            (self.source_b['authority_public'],self.source_b['authority_pin']),
            (self.notaries['notary_a_public'],self.notaries['notary_a_pin']),
            (self.notaries['notary_b_public'],self.notaries['notary_b_pin']),
        )

    def certificate(self,idx,*,snapshot=None,change=None):
        saved=self.initial if snapshot is None else snapshot
        body={
            'schema':high.SCHEMA,
            'operator_id':'offhost-highwater-%s'%('a' if idx==0 else 'b'),
            'checkpoint_scope':self.scope,
            'seal_sequence':self.floors[idx],
            'generation':saved['generation'],
            'event_head_sha256':saved['event_head_sha256'],
            'pair_sha256':saved['pair_sha256'],
            'event_count':saved['event_count'],
            'source_a_sequence':saved['source_a_sequence'],
            'source_b_sequence':saved['source_b_sequence'],
            'witness_fence_retirement_authorized':False,
        }
        body.update(change or {})
        self.serial+=1
        out=Path(self.temp.name)/('seal-%d.json'%self.serial)
        _sign(body,high.SCHEMA,high.DOMAIN,self.observers[idx][0],out)
        return out.read_bytes()

    def inputs(self):
        return dict(
            scope=self.scope,
            operator_a_id='offhost-highwater-a',
            operator_b_id='offhost-highwater-b',
            operator_a_public=self.observers[0][1],
            operator_a_pin=self.observers[0][2],
            operator_b_public=self.observers[1][1],
            operator_b_pin=self.observers[1][2],
            external_a_sha256=self.hash_a,
            external_b_sha256=self.hash_b,
            external_a_sequence_floor=self.floors[0],
            external_b_sequence_floor=self.floors[1],
            expected_generation=self.initial['generation'],
            expected_pair_pin=self.initial['pair_sha256'],
            expected_event_head=self.initial['event_head_sha256'],
            excluded_pinned_public_keys=self.identities(),
        )

    def check(self,*,signed_a=None,signed_b=None,**change):
        inputs=self.inputs()
        inputs.update(change)
        return high.verify(self.db,
            self.cert_a if signed_a is None else signed_a,
            self.cert_b if signed_b is None else signed_b,**inputs)

    def _anchors_at(self,snapshot):
        self.cert_a=self.certificate(0,snapshot=snapshot)
        self.cert_b=self.certificate(1,snapshot=snapshot)
        self.hash_a=hashlib.sha256(self.cert_a).hexdigest()
        self.hash_b=hashlib.sha256(self.cert_b).hexdigest()

    def test_matching_operators_anchor_full_genesis_chain(self):
        result=self.check()
        self.assertTrue(result['two_distinct_pinned_operator_ed25519_seals_verified'])
        self.assertEqual(result['signed_floor_generation'],0)
        self.assertEqual(result['observed_head_generation'],0)
        self.assertFalse(result['witness_fence_retired'])

    def test_keeper_may_strictly_advance_beyond_signed_floor(self):
        new=self._advanced_keeper()
        result=self.check(expected_generation=1,
                          expected_pair_pin=new['pair_sha256'],
                          expected_event_head=new['event_head_sha256'])
        self.assertEqual(result['signed_floor_generation'],0)
        self.assertEqual(result['observed_head_generation'],1)

    def test_signed_newer_floor_exposes_coordinated_rollback(self):
        # An attacker restores an old complete DB and supplies matching old
        # "external" head pins; two stale network replies could also agree.
        old_snapshot=Path(self.temp.name)/'old-db.copy'
        shutil.copyfile(self.db,old_snapshot)
        latest=self._advanced_keeper()
        self._anchors_at(latest)
        shutil.copyfile(old_snapshot,self.db)
        self.db.chmod(0o600)
        with self.assertRaises(high.HighwaterConflict):
            self.check()

    def test_signed_latest_floor_matches_latest_chain(self):
        new=self._advanced_keeper()
        self._anchors_at(new)
        report=self.check(expected_generation=1,
                          expected_pair_pin=new['pair_sha256'],
                          expected_event_head=new['event_head_sha256'])
        self.assertEqual(report['signed_floor_generation'],1)

    def test_signed_older_replaced_event_hash_rejected(self):
        new=self._advanced_keeper()
        self._anchors_at(new)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE checkpoint_events SET pair_sha256=? WHERE generation=1",
                        ('f'*64,))
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(expected_generation=1,expected_pair_pin=new['pair_sha256'],
                       expected_event_head=new['event_head_sha256'])

    def test_signed_operator_quorum_disagreement_rejected(self):
        other=self.certificate(1,change={'event_count':2})
        with self.assertRaises(high.HighwaterConflict):
            self.check(signed_b=other,external_b_sha256=
                       hashlib.sha256(other).hexdigest())

    def test_same_operator_id_is_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(operator_b_id='offhost-highwater-a')

    def test_same_observer_public_key_is_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(operator_b_public=self.observers[0][1],
                       operator_b_pin=self.observers[0][2])

    def test_observer_key_equal_authority_key_is_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(operator_a_public=self.source_a['authority_public'],
                       operator_a_pin=self.source_a['authority_pin'])

    def test_observer_key_equal_notary_key_is_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(operator_b_public=self.notaries['notary_b_public'],
                       operator_b_pin=self.notaries['notary_b_pin'])

    def test_changed_external_signed_envelope_pin_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(external_a_sha256='f'*64)

    def test_missing_independent_envelope_pin_rejected(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(external_a_sha256='invalid')

    def test_old_observer_sequence_below_independent_floor_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(external_a_sequence_floor=self.floors[0]+1)

    def test_operator_b_sequence_below_independent_floor_rejected(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(external_b_sequence_floor=self.floors[1]+1)

    def test_notary_seal_collision_refused(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(excluded_pinned_public_keys=(
                *self.identities(),(self.observers[0][1],self.observers[0][2])))

    def test_bad_signed_signature_refused(self):
        obj=json.loads(self.cert_a)
        obj['signature_hex']='0'*128
        raw=json.dumps(obj).encode()
        with self.assertRaises(ValueError):
            self.check(signed_a=raw,external_a_sha256=
                       hashlib.sha256(raw).hexdigest())

    def test_duplicate_signed_field_refused(self):
        raw=self.cert_a[:-1]+b',"schema":"fake"}'
        with self.assertRaises(ValueError):
            self.check(signed_a=raw,external_a_sha256=
                       hashlib.sha256(raw).hexdigest())

    def test_swapped_observer_seals_refused(self):
        with self.assertRaises(ValueError):
            self.check(signed_a=self.cert_b,signed_b=self.cert_a,
                       external_a_sha256=self.hash_b,
                       external_b_sha256=self.hash_a)

    def test_wrong_scope_refused(self):
        with self.assertRaises(high.HighwaterConflict):
            self.check(scope='another-private-scope')

    def test_release_flag_is_never_allowed(self):
        raw=self.certificate(0,change={'witness_fence_retirement_authorized':True})
        with self.assertRaises(high.HighwaterConflict):
            self.check(signed_a=raw,external_a_sha256=
                       hashlib.sha256(raw).hexdigest())

    def test_boolean_seal_generation_rejected(self):
        raw=self.certificate(0,change={'generation':True})
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(signed_a=raw,external_a_sha256=
                       hashlib.sha256(raw).hexdigest())

    def test_boolean_seal_count_rejected(self):
        raw=self.certificate(0,change={'event_count':True})
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(signed_a=raw,external_a_sha256=
                       hashlib.sha256(raw).hexdigest())

    def test_keeper_changed_between_two_reads_refused(self):
        original=recovery_snapshot(self.db)
        new=self._advanced_keeper()
        advanced=recovery_snapshot(self.db)
        with mock.patch.object(high.recovery,'_snapshot',
                               side_effect=[original,advanced]):
            with self.assertRaises(high.HighwaterConflict):
                self.check(expected_generation=1,
                           expected_pair_pin=new['pair_sha256'],
                           expected_event_head=new['event_head_sha256'])

    def test_missing_keeper_never_created(self):
        self.db.unlink()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check()
        self.assertFalse(self.db.exists())

    def test_anchored_floor_cannot_be_newer_than_actual_db(self):
        raw_a=self.certificate(0,change={'generation':2})
        raw_b=self.certificate(1,change={'generation':2})
        with self.assertRaises(high.HighwaterConflict):
            self.check(signed_a=raw_a,signed_b=raw_b,
                       external_a_sha256=hashlib.sha256(raw_a).hexdigest(),
                       external_b_sha256=hashlib.sha256(raw_b).hexdigest())

    def test_offline_observation_disclaims_real_independent_storage(self):
        r=self.check()
        self.assertFalse(r['externally_retained_pins_are_latest_proved'])
        self.assertFalse(r['coordinated_rollback_with_compromised_external_pins_excluded'])
        self.assertFalse(r['two_signed_observer_certificates_are_from_deployed_external_hosts_proved'])
        self.assertFalse(r['automatic_cas_retry_authorized'])

    def test_integrated_fresh_dual_source_with_historical_floor(self):
        live_args=dict(
            archived_signed_a=self.old_raw_a,
            archived_signed_b=self.old_raw_b,
            archived_nonce_a=self.old['challenge_a'],
            archived_nonce_b=self.old['challenge_b'],
            source_a=self.source_a,source_b=self.source_b,
            notaries=self.notaries,scope=self.scope,
            expected=self.expected,
            expected_generation=0,expected_pair_pin=self.pin,
            expected_event_head=self.initial['event_head_sha256'],
            fetcher=self.fetch,challenges=self.nonces)
        r=high.verify_with_live_sources(self.db,self.cert_a,self.cert_b,
            highwater_args=self.inputs(),reconnect_args=live_args)
        self.assertTrue(r['fresh_dual_source_checkpoint_agrees_with_signed_historical_floor'])
        self.assertEqual((r['fresh_authority_a_sequence'],
                          r['fresh_authority_b_sequence']),(7,11))

    def test_integrated_two_sources_colluding_on_stale_head_detected(self):
        old=Path(self.temp.name)/'pre-advance.copy'
        shutil.copyfile(self.db,old)
        advanced=self._advanced_keeper()
        self._anchors_at(advanced)
        shutil.copyfile(old,self.db)
        self.db.chmod(0o600)
        args=dict(
            archived_signed_a=self.old_raw_a,
            archived_signed_b=self.old_raw_b,
            archived_nonce_a=self.old['challenge_a'],
            archived_nonce_b=self.old['challenge_b'],
            source_a=self.source_a,source_b=self.source_b,
            notaries=self.notaries,scope=self.scope,
            expected=self.expected,
            expected_generation=0,expected_pair_pin=self.pin,
            expected_event_head=self.initial['event_head_sha256'],
            fetcher=self.fetch,challenges=self.nonces)
        with self.assertRaises(high.HighwaterConflict):
            high.verify_with_live_sources(self.db,self.cert_a,self.cert_b,
                highwater_args=self.inputs(),reconnect_args=args)
        self.assertEqual(self.calls,[])

    def test_integrated_combined_inputs_cannot_change_head_binding(self):
        live_args=dict(
            archived_signed_a=self.old_raw_a,
            archived_signed_b=self.old_raw_b,
            archived_nonce_a=self.old['challenge_a'],
            archived_nonce_b=self.old['challenge_b'],
            source_a=self.source_a,source_b=self.source_b,
            notaries=self.notaries,scope=self.scope,
            expected=self.expected,
            expected_generation=0,expected_pair_pin='f'*64,
            expected_event_head=self.initial['event_head_sha256'],
            fetcher=self.fetch,challenges=self.nonces)
        with self.assertRaises(high.HighwaterConflict):
            high.verify_with_live_sources(self.db,self.cert_a,self.cert_b,
                highwater_args=self.inputs(),reconnect_args=live_args)
        self.assertEqual(self.calls,[])

    def test_integrated_four_live_role_keys_always_cross_pinned(self):
        args=dict(
            archived_signed_a=self.old_raw_a,
            archived_signed_b=self.old_raw_b,
            archived_nonce_a=self.old['challenge_a'],
            archived_nonce_b=self.old['challenge_b'],
            source_a=self.source_a,source_b=self.source_b,
            notaries=self.notaries,scope=self.scope,
            expected=self.expected,
            expected_generation=0,expected_pair_pin=self.pin,
            expected_event_head=self.initial['event_head_sha256'],
            fetcher=self.fetch,challenges=self.nonces)
        high_args=self.inputs()
        high_args.pop('excluded_pinned_public_keys')
        accepted=high.verify_with_live_sources(
            self.db,self.cert_a,self.cert_b,
            highwater_args=high_args,reconnect_args=args)
        self.assertTrue(accepted[
            'fresh_dual_source_checkpoint_agrees_with_signed_historical_floor'])

    def test_cli_conflict_redacted_and_no_fence_release(self):
        a=Path(self.temp.name)/'operator-a.json'
        b=Path(self.temp.name)/'operator-b.json'
        a.write_bytes(self.cert_a)
        b.write_bytes(self.cert_b)
        a.chmod(0o600)
        b.chmod(0o600)
        args=[str(self.db),'--scope',self.scope,
              '--expected-generation','0',
              '--expected-pair-pin',self.pin,
              '--expected-event-head',self.initial['event_head_sha256']]
        for name,idx,path,pin in (
                ('a',0,a,self.hash_a),('b',1,b,self.hash_b)):
            args.extend([
                '--operator-'+name+'-id','offhost-highwater-'+name,
                '--operator-'+name+'-public',str(self.observers[idx][1]),
                '--operator-'+name+'-pin',self.observers[idx][2],
                '--signed-'+name+'-checkpoint',str(path),
                '--external-'+name+'-sha256','f'*64 if idx==1 else pin,
                '--external-'+name+'-sequence-floor',str(self.floors[idx]),
            ])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=high.main(args)
        self.assertEqual(status,1)
        obj=json.loads(out.getvalue())
        self.assertFalse(obj['witness_fence_retired'])
        self.assertFalse(obj['automatic_cas_retry_authorized'])
        self.assertTrue(obj['independent_floor_conflict'])
        self.assertNotIn('signature_hex',out.getvalue())


def recovery_snapshot(path):
    from tools import audit_record_witness_publication_cas_reconciliation as recovery
    return recovery._snapshot(path)


if __name__ == '__main__':
    unittest.main()
