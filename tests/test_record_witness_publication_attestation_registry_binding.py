"""Stage 264P: mirrored signing ledgers must bind real pinned Ed25519 outputs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest import mock

from tests import test_record_witness_publication_attestation_nonce_guard as fixture
from tools import audit_record_witness_publication_attestation_registry_binding as bound
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_attestation_nonce_guard as guard
from tools import audit_record_witness_publication_nonce_divergence_attestations as signed
from tools.audit_record_anchor_handoff import _canonical


class MirroredAttestationBindingTests(unittest.TestCase):
    setUpClass=fixture.GuardedDivergenceAttestationTests.__dict__['setUpClass']
    tearDownClass=fixture.GuardedDivergenceAttestationTests.__dict__['tearDownClass']

    def setUp(self):
        fixture.GuardedDivergenceAttestationTests.setUp(self)
        self.mirror_dir=Path(self.temp.name)/'separately-verified-registry'
        self.mirror_dir.mkdir(mode=0o700)
        self.mirror_dir.chmod(0o700)
        self.mirror=self.mirror_dir/'second-operator-view.db'
        self.manifest=Path(self.temp.name)/'signed-bindings-manifest.json'
        self.complete={'operator-a':[],'operator-b':[]}

    def advance(self,operator=0,**kw):
        args={'expected_registry_head':ledger.snapshot(
            self.guard_path)['latest_ledger_sha256']}
        args.update(kw)
        r=self.guarded(operator,**args)
        name=('operator-a','operator-b')[operator]
        self.complete[name].append((
            self.receipt_paths[operator].read_bytes(),
            r['attestation_envelope_sha256']))
        return r

    def seal_mirror(self):
        shutil.copyfile(self.guard_path,self.mirror)
        self.mirror.chmod(0o600)

    def params(self):
        head=ledger.snapshot(self.guard_path)['latest_ledger_sha256']
        return dict(primary_head_pin=head,secondary_head_pin=head,
            primary_genesis_pin=self.genesis,
            secondary_genesis_pin=self.genesis,
            scope=self.scope,operator_a_public=self.observers[0][1],
            operator_b_public=self.observers[1][1],
            signed_envelopes=self.complete)

    def check_mirror(self,**overrides):
        p=self.params()
        p.update(overrides)
        return bound.verify(self.guard_path,self.mirror,**p)

    def one_complete(self):
        self.advance()
        self.seal_mirror()

    def test_success_single_signed_completion_two_private_ledgers(self):
        self.one_complete()
        r=self.check_mirror()
        self.assertEqual(r['verified_signed_completion_count'],1)
        self.assertEqual(r['verified_event_count'],2)
        self.assertTrue(r['all_ed25519_signatures_bind_canonical_pre_sign_body'])
        self.assertFalse(r['offhost_operator_independence_proved'])

    def test_success_two_operator_signatures_bound_to_same_history(self):
        self.advance()
        self.advance(1)
        self.seal_mirror()
        r=self.check_mirror()
        self.assertEqual(r['verified_signed_completion_count'],2)
        self.assertEqual(r['pending_operator_roles'],[])

    def test_extra_pending_reservation_is_not_a_completed_signature(self):
        self.advance()
        first=ledger.snapshot(self.guard_path)['latest_ledger_sha256']
        fields=dict(scope=self.scope,role='operator-b',
            operator_id=self.enrolled['operator-b']['operator_id'],
            storage_id=self.storages[1],
            operator_public_pin=self.observers[1][2],
            nonce='e'*32,seq=1,previous=self.previous[1],
            archive_pin=self.archive_pin,evidence_pin='f'*64)
        ledger._record(self.guard_path,action='reserve',
                       expected_head=first,**fields)
        self.seal_mirror()
        r=self.check_mirror()
        self.assertEqual(r['verified_signed_completion_count'],1)
        self.assertEqual(r['pending_operator_roles'],['operator-b'])

    def test_pending_only_is_not_evidence_of_signed_completion(self):
        state=ledger.snapshot(self.guard_path)
        ledger._record(self.guard_path,action='reserve',
            expected_head=state['latest_ledger_sha256'],
            scope=self.scope,role='operator-a',operator_id=self.enrolled['operator-a']['operator_id'],
            storage_id=self.storages[0],operator_public_pin=self.observers[0][2],
            nonce=self.challenge[0],seq=1,previous=self.previous[0],
            archive_pin=self.archive_pin,evidence_pin='e'*64)
        self.seal_mirror()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror()

    def test_zero_completed_events_is_not_signed_authority(self):
        self.seal_mirror()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror()

    def test_missing_signed_envelope_fails_even_if_histories_match(self):
        self.one_complete()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={'operator-a':[],'operator-b':[]})

    def test_missing_required_role_in_manifest_fails(self):
        self.one_complete()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={'operator-a':self.complete['operator-a']})

    def test_extra_signed_envelope_fails(self):
        self.one_complete()
        duplicate=self.complete['operator-a'][0]
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={
                'operator-a':[duplicate,duplicate],'operator-b':[]})

    def test_swapped_operator_envelope_fails(self):
        self.advance()
        self.advance(1)
        self.seal_mirror()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={
                'operator-a':self.complete['operator-b'],
                'operator-b':self.complete['operator-a']})

    def test_wrong_independent_signed_envelope_pin_fails(self):
        self.one_complete()
        original=self.complete['operator-a'][0]
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={
                'operator-a':[(original[0],'f'*64)],'operator-b':[]})

    def test_tampered_signed_bytes_with_new_local_hash_fail_signature(self):
        self.one_complete()
        raw=self.complete['operator-a'][0][0]
        altered=raw[:-1]+b' '
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={
                'operator-a':[(altered,hashlib.sha256(altered).hexdigest())],
                'operator-b':[]})

    def test_wrong_public_key_is_rejected(self):
        self.one_complete()
        with self.assertRaises((ValueError,bound.SignedLedgerConflict)):
            self.check_mirror(operator_a_public=self.observers[1][1])

    def test_mirror_stale_prefix_is_not_authorized(self):
        self.seal_mirror()
        self.advance()
        with self.assertRaises((bound.SignedLedgerConflict,cross.LedgerDivergence)):
            self.check_mirror()

    def test_forked_mirror_does_not_pass_signed_binding(self):
        self.one_complete()
        mirror=ledger.snapshot(self.mirror)['latest_ledger_sha256']
        ledger._record(self.mirror,action='reserve',
            expected_head=mirror,scope=self.scope,role='operator-b',
            operator_id=self.enrolled['operator-b']['operator_id'],
            storage_id=self.storages[1],operator_public_pin=self.observers[1][2],
            nonce='e'*32,seq=1,previous=self.previous[1],
            archive_pin=self.archive_pin,evidence_pin='f'*64)
        with self.assertRaises((bound.SignedLedgerConflict,cross.LedgerDivergence)):
            self.check_mirror(secondary_head_pin=ledger.snapshot(
                self.mirror)['latest_ledger_sha256'])

    def test_rollback_to_stale_external_head_is_rejected(self):
        self.one_complete()
        with self.assertRaises((bound.SignedLedgerConflict,cross.LedgerDivergence)):
            self.check_mirror(primary_head_pin=self.genesis)

    def test_same_file_alias_rejected(self):
        self.one_complete()
        with self.assertRaises((bound.SignedLedgerConflict,cross.LedgerDivergence)):
            bound.verify(self.guard_path,self.guard_path,**self.params())

    def test_hardlinked_mirror_rejected(self):
        self.one_complete()
        self.mirror.unlink()
        os.link(self.guard_path,self.mirror)
        with self.assertRaises((bound.SignedLedgerConflict,cross.LedgerDivergence,ledger.CheckpointCASConflict)):
            self.check_mirror()

    def test_world_readable_mirror_rejected(self):
        self.one_complete()
        self.mirror.chmod(0o644)
        with self.assertRaises((ValueError,bound.SignedLedgerConflict)):
            self.check_mirror()

    def test_no_valid_signature_after_forged_release_flag(self):
        self.one_complete()
        body=self.body_for(0)
        body['witness_fence_retirement_authorized']=True
        private=Path(self.temp.name)/'forged.json'
        from tools.audit_record_witness_fence_reconciliation import _sign
        _sign(body,signed.SCHEMA,signed.DOMAIN,self.observers[0][0],private)
        raw=private.read_bytes()
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(signed_envelopes={
                'operator-a':[(raw,hashlib.sha256(raw).hexdigest())],
                'operator-b':[]})

    def test_low_level_mismatched_reservation_commitment_refused(self):
        self.one_complete()
        # Signed receipt is authentic and both ledgers can still hash-audit
        # after altering a reserve+complete commitment and recomputing all
        # event heads. The Stage P signing-body binding MUST catch this.
        for db in (self.guard_path,self.mirror):
            with sqlite3.connect(db) as con:
                con.execute("UPDATE events SET evidence_sha256=? WHERE event_id IN (1,2)",
                            ('f'*64,))
                entries=con.execute('SELECT '+','.join(ledger.FIELDS)+
                                    ' FROM events ORDER BY event_id').fetchall()
                head=self.genesis
                for values in entries:
                    e=dict(zip(ledger.FIELDS,values))
                    e['previous_event_sha256']=head
                    head=ledger._hash_event(e)
                    con.execute('UPDATE events SET previous_event_sha256=?,event_sha256=? WHERE event_id=?',
                                (e['previous_event_sha256'],head,e['event_id']))
        forged_head=ledger.snapshot(self.guard_path)['latest_ledger_sha256']
        with self.assertRaises(bound.SignedLedgerConflict):
            self.check_mirror(primary_head_pin=forged_head,
                              secondary_head_pin=forged_head)

    def test_success_report_disclaims_distributed_cas_and_fence_release(self):
        self.one_complete()
        r=self.check_mirror()
        for key in ('globally_unique_nonce_registry_proved',
                    'offhost_operator_independence_proved',
                    'independent_retention_of_external_pins_proved',
                    'actual_private_archive_inspection_proved',
                    'atomic_cross_host_signing_proved',
                    'automatic_register_sync_authorized',
                    'automatic_cas_retry_authorized',
                    'witness_fence_retirement_authorized',
                    'witness_fence_retired','native_switch_game_build_verified'):
            self.assertFalse(r[key],key)

    def build_manifest(self):
        obj={}
        for role,items in self.complete.items():
            obj[role]=[]
            for i,(raw,pin) in enumerate(items):
                path=Path(self.temp.name)/(role+'-signed-%d.json'%i)
                path.write_bytes(raw)
                path.chmod(0o600)
                obj[role].append({'path':str(path),'sha256':pin})
        self.manifest.write_bytes(_canonical(obj))
        self.manifest.chmod(0o600)

    def cli_args(self):
        s=self.params()
        return [str(self.guard_path),str(self.mirror),
            '--scope',self.scope,
            '--primary-head-pin',s['primary_head_pin'],
            '--secondary-head-pin',s['secondary_head_pin'],
            '--primary-genesis-pin',s['primary_genesis_pin'],
            '--secondary-genesis-pin',s['secondary_genesis_pin'],
            '--operator-a-public',str(self.observers[0][1]),
            '--operator-b-public',str(self.observers[1][1]),
            '--private-signed-manifest',str(self.manifest)]

    def test_cli_signed_mirror_success_redacted(self):
        self.one_complete()
        self.build_manifest()
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli_args())
        self.assertEqual(code,0,out.getvalue())
        data=json.loads(out.getvalue())
        self.assertEqual(data['verified_signed_completion_count'],1)
        self.assertFalse(data['witness_fence_retired'])
        self.assertNotIn(self.challenge[0],out.getvalue())

    def test_cli_incomplete_manifest_fails_closed(self):
        self.one_complete()
        self.manifest.write_bytes(b'{}')
        self.manifest.chmod(0o600)
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli_args())
        self.assertEqual(code,1)
        self.assertTrue(json.loads(out.getvalue())['signed_registry_binding_conflict'])

    def test_cli_missing_manifest_fails_without_creating_file(self):
        self.one_complete()
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli_args())
        self.assertEqual(code,1)
        self.assertFalse(self.manifest.exists())

    def test_cli_modified_signed_pin_fails_closed(self):
        self.one_complete()
        self.build_manifest()
        data=json.loads(self.manifest.read_bytes())
        data['operator-a'][0]['sha256']='e'*64
        self.manifest.write_bytes(_canonical(data))
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=bound.main(self.cli_args())
        self.assertEqual(code,1)
        self.assertTrue(json.loads(out.getvalue())['signed_registry_binding_conflict'])


# Reuse complex isolated witness fixtures without inheriting their own tests.
for name in ('sign','compute_pin','fetch','_advanced_keeper','certificate',
             'body','endorse','bundle','args','check','create','inspect',
             'arguments','copy_args','clone','signed_body','sign_receipt',
             'operator_args','make_fields','reserve','sign_one','kwargs',
             'crosscheck','write','create_witness','inspect_witness',
             'trusted','body_for','make_signed','checked','issue',
             'guarded','cli','snapshot'):
    if hasattr(fixture.GuardedDivergenceAttestationTests,name):
        setattr(MirroredAttestationBindingTests,name,
                getattr(fixture.GuardedDivergenceAttestationTests,name))


if __name__=='__main__':
    unittest.main()
