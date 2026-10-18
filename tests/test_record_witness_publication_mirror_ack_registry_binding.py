"""Stage 264T: each mirrored completed ack must match a real Ed25519 envelope."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest

from tests import test_record_witness_publication_mirror_ack_nonce_guard as previous
from tools import audit_record_witness_publication_mirror_ack_registry_binding as bound
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools import audit_record_witness_publication_signed_mirror_acknowledgments as mirror
from tools.audit_record_witness_fence_reconciliation import _sign
from tools.audit_record_anchor_handoff import _canonical

FAIL=(ValueError,OSError,cross.LedgerDivergence,cas.CheckpointCASConflict,
      sqlite3.DatabaseError)


class MirrorAcknowledgmentRegistryBindingTests(unittest.TestCase):
    setUpClass=previous.MirrorAcknowledgmentNonceGuardTests.__dict__['setUpClass']
    tearDownClass=previous.MirrorAcknowledgmentNonceGuardTests.__dict__['tearDownClass']

    def setUp(self):
        previous.MirrorAcknowledgmentNonceGuardTests.setUp(self)
        self.attestations={'operator-a':[],'operator-b':[]}
        self.private_mirror_dir=Path(self.temp.name)/'second-private-ack-history'
        self.private_mirror_dir.mkdir(mode=0o700)
        self.secondary_ack=self.private_mirror_dir/'separate-ack-ledger.db'
        self.manifest_acks=Path(self.temp.name)/'private-ack-manifest.json'

    def issue_ack(self,i=0,**kw):
        head=ledger.snapshot(self.ack_registry)['latest_ledger_sha256']
        item=self.sign_guarded_ack(i,expected_registry_head=head,**kw)
        role=('operator-a','operator-b')[i]
        output=kw.get('output',self.paths[i])
        raw=Path(output).read_bytes()
        self.attestations[role].append((raw,item['acknowledgment_sha256']))
        return item

    def mirror_acks(self):
        shutil.copyfile(self.ack_registry,self.secondary_ack)
        self.secondary_ack.chmod(0o600)

    def trusted_acks(self):
        state=ledger.snapshot(self.ack_registry)
        return dict(
            primary_head_pin=state['latest_ledger_sha256'],
            secondary_head_pin=state['latest_ledger_sha256'],
            primary_genesis_pin=self.ack_genesis,
            secondary_genesis_pin=self.ack_genesis,
            scope=self.scope,operator_a_public=self.observers[0][1],
            operator_b_public=self.observers[1][1],
            signed_envelopes=self.attestations)

    def audit_acks(self,**changes):
        opts=self.trusted_acks()
        opts.update(changes)
        return bound.verify(self.ack_registry,self.secondary_ack,**opts)

    def first(self):
        self.issue_ack()
        self.mirror_acks()

    def test_single_completed_signed_acknowledgment_verified(self):
        self.first()
        r=self.audit_acks()
        self.assertEqual(r['verified_completed_acknowledgment_count'],1)
        self.assertEqual(r['verified_event_count'],2)
        self.assertEqual(r['pending_operator_roles'],[])
        self.assertTrue(r['all_completed_acknowledgment_signatures_bind_pre_sign_reservations'])

    def test_two_distinct_roles_each_have_signed_acknowledgment(self):
        self.issue_ack()
        self.issue_ack(1)
        self.mirror_acks()
        r=self.audit_acks()
        self.assertEqual(r['verified_completed_acknowledgment_count'],2)
        self.assertEqual(r['verified_event_count'],4)

    def test_pending_second_role_cannot_claim_completed_receipt(self):
        self.issue_ack()
        head=ledger.snapshot(self.ack_registry)['latest_ledger_sha256']
        ledger._record(self.ack_registry,action='reserve',
            expected_head=head,scope=self.scope,role='operator-b',
            operator_id=self.ack_enrollment['operator-b']['operator_id'],
            storage_id=self.stores[1],
            operator_public_pin=self.observers[1][2],
            nonce='c'*32,seq=1,previous=self.previous[1],
            archive_pin='e'*64,evidence_pin='f'*64)
        self.mirror_acks()
        r=self.audit_acks()
        self.assertEqual(r['verified_completed_acknowledgment_count'],1)
        self.assertEqual(r['pending_operator_roles'],['operator-b'])

    def test_empty_registries_are_not_evidence_of_completed_signatures(self):
        self.mirror_acks()
        with self.assertRaises(FAIL):
            self.audit_acks()

    def test_missing_envelope_rejected(self):
        self.first()
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={'operator-a':[],'operator-b':[]})

    def test_missing_role_manifest_rejected(self):
        self.first()
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={'operator-a':self.attestations['operator-a']})

    def test_extra_envelope_cannot_duplicate_one_completion(self):
        self.first()
        pair=self.attestations['operator-a'][0]
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={'operator-a':[pair,pair],
                                              'operator-b':[]})

    def test_wrong_exact_signed_envelope_pin_rejected(self):
        self.first()
        raw,_=self.attestations['operator-a'][0]
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={
                'operator-a':[(raw,'f'*64)],'operator-b':[]})

    def test_forged_signed_bytes_with_self_supplied_pin_rejected(self):
        self.first()
        raw,_=self.attestations['operator-a'][0]
        bad=raw[:-1]+b' '
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={
                'operator-a':[(bad,hashlib.sha256(bad).hexdigest())],
                'operator-b':[]})

    def test_authentically_signed_but_different_body_cannot_replace_complete(self):
        self.first()
        altered=self.expected_ack_body(0,
            exact_signed_completion_manifest_sha256='f'*64)
        forged=Path(self.temp.name)/'different-valid-signature.json'
        _sign(altered,mirror.SCHEMA,mirror.DOMAIN,self.observers[0][0],forged)
        raw=forged.read_bytes()
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={
                'operator-a':[(raw,hashlib.sha256(raw).hexdigest())],
                'operator-b':[]})

    def test_swapped_role_signatures_rejected(self):
        self.issue_ack()
        self.issue_ack(1)
        self.mirror_acks()
        with self.assertRaises(FAIL):
            self.audit_acks(signed_envelopes={
                'operator-a':self.attestations['operator-b'],
                'operator-b':self.attestations['operator-a']})

    def test_different_registered_public_key_is_not_allowed(self):
        self.first()
        with self.assertRaises(FAIL):
            self.audit_acks(operator_a_public=self.observers[1][1])

    def test_missing_secondary_registry_rejected(self):
        self.issue_ack()
        with self.assertRaises(FAIL):
            self.audit_acks()

    def test_prefix_lag_rejected_with_different_external_heads(self):
        self.mirror_acks()
        self.issue_ack()
        kw=self.trusted_acks()
        kw['secondary_head_pin']=self.ack_genesis
        with self.assertRaises(FAIL):
            self.audit_acks(**kw)

    def test_forked_second_registry_rejected_even_if_individually_audited(self):
        self.first()
        head=ledger.snapshot(self.secondary_ack)['latest_ledger_sha256']
        ledger._record(self.secondary_ack,action='reserve',
            expected_head=head,scope=self.scope,role='operator-b',
            operator_id=self.ack_enrollment['operator-b']['operator_id'],
            storage_id=self.stores[1],operator_public_pin=self.observers[1][2],
            nonce='c'*32,seq=1,previous=self.previous[1],
            archive_pin='f'*64,evidence_pin='e'*64)
        with self.assertRaises(FAIL):
            self.audit_acks(secondary_head_pin=ledger.snapshot(
                self.secondary_ack)['latest_ledger_sha256'])

    def test_stale_externally_pinned_head_is_not_accepted(self):
        self.first()
        with self.assertRaises(FAIL):
            self.audit_acks(primary_head_pin=self.ack_genesis)

    def test_wrong_enrollment_genesis_rejected(self):
        self.first()
        with self.assertRaises(FAIL):
            self.audit_acks(secondary_genesis_pin='f'*64)

    def test_one_path_cannot_be_two_registries(self):
        self.first()
        with self.assertRaises(FAIL):
            bound.verify(self.ack_registry,self.ack_registry,
                         **self.trusted_acks())

    def test_hardlinked_registry_is_rejected(self):
        self.first()
        self.secondary_ack.unlink()
        os.link(self.ack_registry,self.secondary_ack)
        with self.assertRaises(FAIL):
            self.audit_acks()

    def test_publicly_readable_secondary_registry_rejected(self):
        self.first()
        self.secondary_ack.chmod(0o644)
        with self.assertRaises(FAIL):
            self.audit_acks()

    def test_missing_original_source_registries_do_not_forge_inspection_claim(self):
        self.first()
        self.guard_path.unlink()
        self.mirror.unlink()
        report=self.audit_acks()
        self.assertTrue(report['two_private_local_acknowledgment_ledgers_match'])
        self.assertFalse(report['underlying_source_mirror_audits_replayed_proved'])

    def test_disclaimers_for_external_independence_and_no_release(self):
        self.first()
        r=self.audit_acks()
        for key in ('independent_offhost_registry_retention_proved',
                    'independently_trusted_external_pins_proved',
                    'underlying_source_mirror_audits_replayed_proved',
                    'remote_global_nonce_consensus_proved',
                    'physical_operator_independence_proved',
                    'automatic_registry_sync_authorized',
                    'automatic_pending_recovery_authorized',
                    'automatic_cas_retry_authorized',
                    'witness_fence_retirement_authorized',
                    'witness_fence_retired','native_switch_game_build_verified'):
            self.assertFalse(r[key],key)

    def write_manifest(self):
        content={}
        for role,items in self.attestations.items():
            content[role]=[]
            for i,(raw,pin) in enumerate(items):
                path=Path(self.temp.name)/(role+'-completed-mirror-ack-'+str(i)+'.json')
                path.write_bytes(raw)
                path.chmod(0o600)
                content[role].append({'path':str(path),'sha256':pin})
        self.manifest_acks.write_bytes(_canonical(content))
        self.manifest_acks.chmod(0o600)

    def cli(self):
        s=self.trusted_acks()
        return [str(self.ack_registry),str(self.secondary_ack),
            '--primary-head-pin',s['primary_head_pin'],
            '--secondary-head-pin',s['secondary_head_pin'],
            '--primary-genesis-pin',s['primary_genesis_pin'],
            '--secondary-genesis-pin',s['secondary_genesis_pin'],
            '--scope',s['scope'],
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-b-public',str(self.observers[1][1]),
            '--private-signed-manifest',str(self.manifest_acks)]

    def test_cli_success_redacts_signed_details(self):
        self.first()
        self.write_manifest()
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli())
        self.assertEqual(code,0,out.getvalue())
        r=json.loads(out.getvalue())
        self.assertEqual(r['verified_completed_acknowledgment_count'],1)
        self.assertFalse(r['witness_fence_retired'])
        self.assertNotIn(self.nonces[0],out.getvalue())

    def test_cli_rejects_missing_signed_manifest(self):
        self.first()
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli())
        self.assertEqual(code,1)
        self.assertFalse(self.manifest_acks.exists())

    def test_cli_rejects_wrong_private_manifest_pin(self):
        self.first()
        self.write_manifest()
        data=json.loads(self.manifest_acks.read_bytes())
        data['operator-a'][0]['sha256']='e'*64
        self.manifest_acks.write_bytes(_canonical(data))
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli())
        self.assertEqual(code,1)
        self.assertTrue(json.loads(out.getvalue())['acknowledgment_mirror_signature_conflict'])


# Stage S inherits a substantial synthetic Stage A-Q fixture but none of its
# tests. Preserve original methods; never shadow their parameter dictionaries.
for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate','body',
    'endorse','bundle','args','check','create','inspect','arguments',
    'copy_args','clone','signed_body','sign_receipt','operator_args',
    'make_fields','reserve','sign_one','kwargs','crosscheck','write',
    'create_witness','inspect_witness','trusted','body_for','make_signed',
    'checked','issue','guarded','snapshot','advance','seal_mirror',
    'params','check_mirror','one_complete','build_manifest',
    'expected_ack_body','signed_ack','verify','ack_arguments',
    'sign_guarded_ack','ack_snapshot'
):
    if hasattr(previous.MirrorAcknowledgmentNonceGuardTests,name):
        setattr(MirrorAcknowledgmentRegistryBindingTests,name,
                getattr(previous.MirrorAcknowledgmentNonceGuardTests,name))


if __name__=='__main__':
    unittest.main()
