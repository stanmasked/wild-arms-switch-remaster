"""Stage 264E signed two-successor equivocation evidence, synthetic Ed25519."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import unittest

from tests import test_record_witness_publication_highwater_lineage as fixture
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_highwater_equivocation as ev


class EquivocationEvidenceTests(unittest.TestCase):
    setUpClass=fixture.HighwaterLineageTests.__dict__['setUpClass']
    tearDownClass=fixture.HighwaterLineageTests.__dict__['tearDownClass']
    sign=fixture.HighwaterLineageTests.sign
    compute_pin=fixture.HighwaterLineageTests.compute_pin
    fetch=fixture.HighwaterLineageTests.fetch
    _advanced_keeper=fixture.HighwaterLineageTests._advanced_keeper
    certificate=fixture.HighwaterLineageTests.certificate
    body=fixture.HighwaterLineageTests.body
    endorse=fixture.HighwaterLineageTests.endorse

    def setUp(self):
        fixture.HighwaterLineageTests.setUp(self)
        self.parent_a,self.parent_b=self.old_a,self.old_b
        self.branch_a=self.bundle()
        other=dict(self.latest,pair_sha256='9'*64,event_head_sha256='a'*64)
        self.latest=other
        self.new_a=self.certificate(0,snapshot=other)
        self.new_b=self.certificate(1,snapshot=other)
        self.pinned['new_a']=hashlib.sha256(self.new_a).hexdigest()
        self.pinned['new_b']=hashlib.sha256(self.new_b).hexdigest()
        self.signed_a=self.endorse(0)
        self.signed_b=self.endorse(1)
        self.pinned['endorsement_a']=hashlib.sha256(self.signed_a).hexdigest()
        self.pinned['endorsement_b']=hashlib.sha256(self.signed_b).hexdigest()
        self.branch_b=self.bundle()
        self.pins_a={k:hashlib.sha256(v).hexdigest()
                     for k,v in self.branch_a.items()}
        self.pins_b={k:hashlib.sha256(v).hexdigest()
                     for k,v in self.branch_b.items()}

    def bundle(self):
        return dict(old_a=self.parent_a,old_b=self.parent_b,
                    new_a=self.new_a,new_b=self.new_b,
                    endorsement_a=self.signed_a,endorsement_b=self.signed_b)

    def args(self):
        return dict(
            scope=self.scope,operator_a_id='offhost-highwater-a',
            operator_b_id='offhost-highwater-b',
            operator_a_public=self.observers[0][1],
            operator_a_pin=self.observers[0][2],
            operator_b_public=self.observers[1][1],
            operator_b_pin=self.observers[1][2],
            parent_old_a_pin=hashlib.sha256(self.parent_a).hexdigest(),
            parent_old_b_pin=hashlib.sha256(self.parent_b).hexdigest(),
            previous_transition_bundle_sha256=self.previous,
            expected_parent_generation=self.initial['generation'],
            expected_parent_pair_pin=self.initial['pair_sha256'],
            expected_parent_event_head=self.initial['event_head_sha256'])

    def check(self,*,branch_a=None,branch_b=None,pins_a=None,pins_b=None,
              **change):
        args=self.args()
        args.update(change)
        return ev.verify(
            self.branch_a if branch_a is None else branch_a,
            self.branch_b if branch_b is None else branch_b,
            self.pins_a if pins_a is None else pins_a,
            self.pins_b if pins_b is None else pins_b,**args)

    def test_two_contradictory_valid_siblings_detected(self):
        result=self.check()
        self.assertTrue(result['contradictory_successor_checkpoint_states_proved'])
        self.assertTrue(result['two_valid_operator_countersigned_sibling_claims_verified'])
        self.assertEqual(result['parent_generation'],0)
        self.assertEqual(result['conflicting_successor_generation'],1)
        self.assertEqual(len(set(result['conflicting_pair_sha256s'])),2)
        self.assertFalse(result['either_successor_was_committed_to_keeper_proved'])
        self.assertFalse(result['witness_fence_retired'])

    def test_swap_branch_order_same_evidence_digest(self):
        original=self.check()
        swapped=self.check(branch_a=self.branch_b,branch_b=self.branch_a,
                           pins_a=self.pins_b,pins_b=self.pins_a)
        self.assertEqual(original['canonical_evidence_sha256'],
                         swapped['canonical_evidence_sha256'])

    def test_exact_external_evidence_pin_valid(self):
        h=self.check()['canonical_evidence_sha256']
        self.assertEqual(self.check(externally_pinned_evidence_sha256=h)[
            'canonical_evidence_sha256'],h)

    def test_wrong_external_evidence_pin_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(externally_pinned_evidence_sha256='0'*64)

    def test_identical_branches_are_not_equivocation(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=self.branch_a,pins_b=self.pins_a)

    def test_same_new_pair_hash_is_not_conflicting_checkpoint(self):
        # New endorsement bytes / observer seal counters alone are not a
        # divergent checkpoint state, even if bundle hashes differ.
        altered=dict(self.branch_b,new_a=self.branch_a['new_a'],
                     new_b=self.branch_a['new_b'],
                     endorsement_a=self.branch_a['endorsement_a'],
                     endorsement_b=self.branch_a['endorsement_b'])
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=altered,pins_b=self.pins_a)

    def test_missing_second_operator_endorsement_refused(self):
        b=dict(self.branch_b)
        del b['endorsement_b']
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=b)

    def test_unknown_field_refused(self):
        b=dict(self.branch_b,foo=b'not-enrolled')
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=b)

    def test_altered_exact_envelope_hash_refused(self):
        pins=dict(self.pins_b,endorsement_a='f'*64)
        with self.assertRaises(ev.EquivocationConflict):
            self.check(pins_b=pins)

    def test_unknown_external_certificate_pin_refused(self):
        pins=dict(self.pins_a,new_b='a'*64)
        with self.assertRaises(ev.EquivocationConflict):
            self.check(pins_a=pins)

    def test_wrong_independently_enrolled_parent_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(parent_old_a_pin='f'*64)

    def test_parent_generation_mismatch_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(expected_parent_generation=1)

    def test_boolean_parent_generation_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(expected_parent_generation=True)

    def test_parent_pair_mismatch_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(expected_parent_pair_pin='f'*64)

    def test_parent_event_head_mismatch_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(expected_parent_event_head='f'*64)

    def test_wrong_previous_transition_bundle_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(previous_transition_bundle_sha256='f'*64)

    def test_wrong_operator_public_pem_pin_refused(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.check(operator_a_pin='f'*64)

    def test_collapsed_operator_public_keys_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(operator_b_public=self.observers[0][1],
                       operator_b_pin=self.observers[0][2])

    def test_same_operator_name_refused(self):
        with self.assertRaises(ev.EquivocationConflict):
            self.check(operator_b_id='offhost-highwater-a')

    def test_different_parent_raw_bytes_refused(self):
        b=dict(self.branch_b,old_a=self.branch_b['new_a'])
        pins=dict(self.pins_b,old_a=hashlib.sha256(b['old_a']).hexdigest())
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=b,pins_b=pins)

    def test_truncated_signed_endorsement_refused(self):
        b=dict(self.branch_b,endorsement_b=b'')
        pins=dict(self.pins_b,endorsement_b=hashlib.sha256(b'').hexdigest())
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=b,pins_b=pins)

    def test_missing_signature_does_not_turn_digest_into_signature(self):
        raw=json.loads(self.branch_b['endorsement_a'])
        raw['signature_hex']='0'*128
        bad=json.dumps(raw,sort_keys=True).encode()
        b=dict(self.branch_b,endorsement_a=bad)
        pins=dict(self.pins_b,endorsement_a=hashlib.sha256(bad).hexdigest())
        with self.assertRaises(ValueError):
            self.check(branch_b=b,pins_b=pins)

    def test_forged_release_flag_refused(self):
        # Editing the signed body invalidates the signature.
        body=json.loads(self.branch_b['endorsement_b'])
        body['body']['witness_fence_retirement_authorized']=True
        raw=json.dumps(body,sort_keys=True).encode()
        b=dict(self.branch_b,endorsement_b=raw)
        pins=dict(self.pins_b,endorsement_b=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):
            self.check(branch_b=b,pins_b=pins)

    def test_wrong_branch_endorsement_replay_refused(self):
        b=dict(self.branch_b,endorsement_b=self.branch_a['endorsement_b'])
        pins=dict(self.pins_b,endorsement_b=self.pins_a['endorsement_b'])
        with self.assertRaises(ev.EquivocationConflict):
            self.check(branch_b=b,pins_b=pins)

    def test_report_disclaims_actual_commit_and_global_latest(self):
        r=self.check()
        self.assertFalse(r['either_successor_was_committed_to_keeper_proved'])
        self.assertFalse(r['real_independent_operator_custody_proved'])
        self.assertFalse(r['externally_archived_evidence_proved'])
        self.assertFalse(r['global_latest_head_proved'])
        self.assertFalse(r['automatic_cas_retry_authorized'])

    def test_cli_failure_redacted_and_no_fence_release(self):
        names=('old_a','old_b','new_a','new_b','endorsement_a','endorsement_b')
        argv=[
            '--scope',self.scope,
            '--operator-a-id','offhost-highwater-a',
            '--operator-b-id','offhost-highwater-b',
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-a-pin',self.observers[0][2],
            '--operator-b-public',str(self.observers[1][1]),
            '--operator-b-pin',self.observers[1][2],
            '--parent-old-a-sha256',self.pins_a['old_a'],
            '--parent-old-b-sha256',self.pins_a['old_b'],
            '--previous-transition-bundle-sha256',self.previous,
            '--expected-parent-generation','0',
            '--expected-parent-pair-pin',self.initial['pair_sha256'],
            '--expected-parent-event-head',self.initial['event_head_sha256'],
            '--externally-pinned-evidence-sha256','f'*64,
        ]
        for label,bundle,pins in (
            ('left',self.branch_a,self.pins_a),
            ('right',self.branch_b,self.pins_b)):
            for name in names:
                path=Path(self.temp.name)/(label+'-'+name+'.json')
                path.write_bytes(bundle[name])
                path.chmod(0o600)
                flag=label+'-'+name.replace('_','-')
                argv.extend(['--'+flag,str(path),'--'+flag+'-sha256',pins[name]])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            result=ev.main(argv)
        r=json.loads(out.getvalue())
        self.assertEqual(result,1)
        self.assertTrue(r['equivocation_evidence_conflict'])
        self.assertFalse(r['witness_fence_retired'])
        self.assertFalse(r['automatic_cas_retry_authorized'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
