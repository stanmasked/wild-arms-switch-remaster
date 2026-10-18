"""Stage 264K: two fully audited external-head-pinned nonce ledger copies."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest import mock

from tests import test_record_witness_publication_receipt_nonce_ledger as fixture
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_receipt_nonce_ledger as nonce
from tools import audit_record_witness_publication_checkpoint_cas as cas


class TwoNonceLedgerReconciliationTests(unittest.TestCase):
    setUpClass=fixture.ReceiptNonceLedgerTests.__dict__['setUpClass']
    tearDownClass=fixture.ReceiptNonceLedgerTests.__dict__['tearDownClass']
    sign=fixture.ReceiptNonceLedgerTests.sign
    compute_pin=fixture.ReceiptNonceLedgerTests.compute_pin
    fetch=fixture.ReceiptNonceLedgerTests.fetch
    _advanced_keeper=fixture.ReceiptNonceLedgerTests._advanced_keeper
    certificate=fixture.ReceiptNonceLedgerTests.certificate
    body=fixture.ReceiptNonceLedgerTests.body
    endorse=fixture.ReceiptNonceLedgerTests.endorse
    bundle=fixture.ReceiptNonceLedgerTests.bundle
    args=fixture.ReceiptNonceLedgerTests.args
    check=fixture.ReceiptNonceLedgerTests.check
    create=fixture.ReceiptNonceLedgerTests.create
    inspect=fixture.ReceiptNonceLedgerTests.inspect
    arguments=fixture.ReceiptNonceLedgerTests.arguments
    copy_args=fixture.ReceiptNonceLedgerTests.copy_args
    clone=fixture.ReceiptNonceLedgerTests.clone
    signed_body=fixture.ReceiptNonceLedgerTests.signed_body
    sign_receipt=fixture.ReceiptNonceLedgerTests.sign_receipt
    params=fixture.ReceiptNonceLedgerTests.params
    verify=fixture.ReceiptNonceLedgerTests.verify
    attest=fixture.ReceiptNonceLedgerTests.attest
    operator_args=fixture.ReceiptNonceLedgerTests.operator_args
    make_fields=fixture.ReceiptNonceLedgerTests.make_fields
    reserve=fixture.ReceiptNonceLedgerTests.reserve
    sign_one=fixture.ReceiptNonceLedgerTests.sign_one

    def setUp(self):
        fixture.ReceiptNonceLedgerTests.setUp(self)
        self.second_parent=Path(self.temp.name)/'another-private-ledger-folder'
        self.second_parent.mkdir(mode=0o700)
        self.second_parent.chmod(0o700)
        self.secondary=self.second_parent/'nonce-ledger-copy.db'
        shutil.copyfile(self.registry_path,self.secondary)
        self.secondary.chmod(0o600)

    def kwargs(self):
        return dict(
            primary_head_pin=nonce.snapshot(self.registry_path)['latest_ledger_sha256'],
            secondary_head_pin=nonce.snapshot(self.secondary)['latest_ledger_sha256'],
            primary_genesis_pin=self.registry_genesis,
            secondary_genesis_pin=self.registry_genesis,
            expected_scope=self.scope)

    def crosscheck(self,**alter):
        params=self.kwargs()
        params.update(alter)
        return cross.verify(self.registry_path,self.secondary,**params)

    def write(self,path,*,role_idx=0,nonce_value=None,head=None,seq=1,previous=None):
        fields=self.make_fields(role_idx,nonce_value,seq,previous)
        return nonce._record(path,action='reserve',
                             expected_head=self.registry_genesis if head is None else head,
                             **fields)

    def test_identical_empty_genesis_registries_pass(self):
        report=self.crosscheck()
        self.assertTrue(report['both_full_nonce_event_hash_chains_identical'])
        self.assertEqual(report['event_count'],0)
        self.assertFalse(report['offhost_admin_independence_proved'])

    def test_identical_reservations_pass_full_audits(self):
        left=self.write(self.registry_path)
        right=self.write(self.secondary)
        self.assertEqual(left,right)
        self.assertEqual(self.crosscheck()['event_count'],1)

    def test_identical_reservations_and_completions_pass(self):
        for path in (self.registry_path,self.secondary):
            current=self.write(path)
            nonce._record(path,action='complete',expected_head=current,
                          receipt_pin='f'*64,**self.make_fields())
        report=self.crosscheck()
        self.assertEqual(report['event_count'],2)
        self.assertTrue(report['two_read_only_audit_rounds_completed'])

    def test_different_valid_next_nonces_are_a_fork(self):
        self.write(self.registry_path)
        self.write(self.secondary,nonce_value='d'*32)
        with self.assertRaises(cross.LedgerDivergence) as cm:
            self.crosscheck()
        self.assertEqual(cm.exception.kind,'forked_hash_chains')
        self.assertEqual(cm.exception.common_events,0)
        self.assertFalse(cm.exception.duplicate_nonce_claims)

    def test_duplicate_nonce_two_separate_roles_detected(self):
        self.write(self.registry_path,role_idx=0)
        self.write(self.secondary,role_idx=1,nonce_value=self.nonces[0])
        with self.assertRaises(cross.LedgerDivergence) as cm:
            self.crosscheck()
        self.assertEqual(cm.exception.kind,'forked_hash_chains')
        self.assertTrue(cm.exception.duplicate_nonce_claims)

    def test_strict_prefix_lag_rejected(self):
        self.write(self.registry_path)
        with self.assertRaises(cross.LedgerDivergence) as cm:
            self.crosscheck()
        self.assertEqual(cm.exception.kind,'strict_prefix_lag')
        self.assertEqual(cm.exception.common_events,0)

    def test_longer_common_prefix_then_fork_detected(self):
        for path in (self.registry_path,self.secondary):
            head=self.write(path)
            nonce._record(path,action='complete',expected_head=head,
                          receipt_pin='f'*64,**self.make_fields())
        prior=nonce.snapshot(self.registry_path)['latest_ledger_sha256']
        self.write(self.registry_path,head=prior,nonce_value='c'*32,
                   seq=2,previous='f'*64)
        self.write(self.secondary,head=prior,nonce_value='d'*32,
                   seq=2,previous='f'*64)
        with self.assertRaises(cross.LedgerDivergence) as cm:
            self.crosscheck()
        self.assertEqual(cm.exception.kind,'forked_hash_chains')
        self.assertEqual(cm.exception.common_events,2)

    def test_replay_old_external_head_rejected_when_newer_file(self):
        self.write(self.registry_path)
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck(primary_head_pin=self.registry_genesis)

    def test_replaced_db_with_old_copy_rejected_against_earlier_pin(self):
        self.write(self.registry_path)
        pinned=nonce.snapshot(self.registry_path)['latest_ledger_sha256']
        shutil.copyfile(self.secondary,self.registry_path)
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck(primary_head_pin=pinned)

    def test_different_genesis_pins_rejected(self):
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck(secondary_genesis_pin='f'*64)

    def test_wrong_external_scope_rejected(self):
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck(expected_scope='untrusted-scope')

    def test_missing_secondary_rejected(self):
        self.secondary.unlink()
        with self.assertRaises((OSError,ValueError)):
            self.crosscheck()

    def test_same_file_path_rejected(self):
        kw=self.kwargs()
        with self.assertRaises(cross.LedgerDivergence):
            cross.verify(self.registry_path,self.registry_path,**kw)

    def test_two_files_in_same_parent_rejected(self):
        sibling=Path(self.temp.name)/'same-private-folder.db'
        shutil.copyfile(self.registry_path,sibling)
        sibling.chmod(0o600)
        with self.assertRaises(cross.LedgerDivergence):
            cross.verify(self.registry_path,sibling,**self.kwargs())

    def test_hardlinked_registry_rejected(self):
        self.secondary.unlink()
        os.link(self.registry_path,self.secondary)
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck()

    def test_registry_symlink_rejected(self):
        self.secondary.unlink()
        self.secondary.symlink_to(self.registry_path)
        with self.assertRaises((cross.LedgerDivergence,OSError,ValueError)):
            self.crosscheck()

    def test_parent_symlink_rejected(self):
        alias=Path(self.temp.name)/'alias-dir'
        alias.symlink_to(self.second_parent,target_is_directory=True)
        with self.assertRaises((cross.LedgerDivergence,ValueError)):
            cross.verify(self.registry_path,alias/self.secondary.name,
                         **self.kwargs())

    def test_world_accessible_secondary_parent_rejected(self):
        self.second_parent.chmod(0o755)
        self.addCleanup(self.second_parent.chmod,0o700)
        with self.assertRaises(cross.LedgerDivergence):
            self.crosscheck()

    def test_modified_private_sqlite_history_fails_audit(self):
        self.write(self.secondary)
        with sqlite3.connect(self.secondary) as con:
            con.execute('UPDATE events SET nonce=? WHERE event_id=1',
                        ('c'*32,))
        with self.assertRaises((ValueError,cross.LedgerDivergence)):
            self.crosscheck()

    def test_registry_injection_between_rounds_refused(self):
        real=cross._read_once
        calls=[0]
        def mutate(path,**kw):
            calls[0]+=1
            result=real(path,**kw)
            if calls[0]==2:
                new_head=self.write(self.secondary)
                self.assertNotEqual(new_head,self.registry_genesis)
            return result
        with mock.patch.object(cross,'_read_once',side_effect=mutate):
            with self.assertRaises(cross.LedgerDivergence):
                self.crosscheck()

    def test_inode_swap_between_rounds_refused(self):
        real=cross._two_identities
        calls=[0]
        def replace_once(a,b):
            calls[0]+=1
            result=real(a,b)
            if calls[0]==2:
                alternate=self.second_parent/'replacement.db'
                shutil.copyfile(self.secondary,alternate)
                alternate.chmod(0o600)
                os.replace(alternate,self.secondary)
            return result
        with mock.patch.object(cross,'_two_identities',side_effect=replace_once):
            with self.assertRaises(cross.LedgerDivergence):
                self.crosscheck()

    def test_reports_never_authorize_automatic_merge(self):
        result=self.crosscheck()
        for field in (
            'offhost_admin_independence_proved',
            'independent_external_head_persistence_proved',
            'global_nonce_cas_consensus_proved',
            'registry_durability_proved',
            'automatic_ledger_merge_authorized',
            'automatic_cas_retry_authorized',
            'witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(result[field],field)

    def argv(self):
        return [str(self.registry_path),str(self.secondary),
            '--primary-head-pin',nonce.snapshot(
                self.registry_path)['latest_ledger_sha256'],
            '--secondary-head-pin',nonce.snapshot(
                self.secondary)['latest_ledger_sha256'],
            '--primary-genesis-pin',self.registry_genesis,
            '--secondary-genesis-pin',self.registry_genesis,
            '--scope',self.scope]

    def test_cli_success_redacted_and_never_releases_fence(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=cross.main(self.argv())
        r=json.loads(out.getvalue())
        self.assertEqual(status,0,out.getvalue())
        self.assertTrue(r['both_full_nonce_event_hash_chains_identical'])
        self.assertFalse(r['witness_fence_retired'])
        self.assertNotIn(self.nonces[0],out.getvalue())

    def test_cli_fork_returns_diagnostic_but_not_signed_contents(self):
        self.write(self.registry_path,role_idx=0)
        self.write(self.secondary,role_idx=1,nonce_value=self.nonces[0])
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=cross.main(self.argv())
        report=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertEqual(report['conflict_class'],'forked_hash_chains')
        self.assertTrue(report['cross_registry_duplicate_nonce_with_different_claims_detected'])
        self.assertFalse(report['automatic_ledger_merge_authorized'])
        self.assertNotIn(self.nonces[0],out.getvalue())

    def test_cli_absent_external_pin_does_not_audit_as_success(self):
        args=self.argv()
        args[args.index('--secondary-head-pin')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=cross.main(args)
        report=json.loads(out.getvalue())
        self.assertEqual(status,1)
        self.assertTrue(report['nonce_ledger_reconciliation_conflict'])
        self.assertFalse(report['witness_fence_retired'])


if __name__=='__main__':
    unittest.main()
