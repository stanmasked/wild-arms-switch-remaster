"""Stage 264L: synthetic detached nonce-history fork archival and replay."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from tests import test_record_witness_publication_receipt_nonce_reconciliation as prior
from tools import audit_record_witness_publication_receipt_nonce_divergence_evidence as witness
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools.audit_record_anchor_handoff import _canonical


class DetachedNonceHistoryTests(unittest.TestCase):
    setUpClass=prior.TwoNonceLedgerReconciliationTests.__dict__['setUpClass']
    tearDownClass=prior.TwoNonceLedgerReconciliationTests.__dict__['tearDownClass']
    sign=prior.TwoNonceLedgerReconciliationTests.sign
    compute_pin=prior.TwoNonceLedgerReconciliationTests.compute_pin
    fetch=prior.TwoNonceLedgerReconciliationTests.fetch
    _advanced_keeper=prior.TwoNonceLedgerReconciliationTests._advanced_keeper
    certificate=prior.TwoNonceLedgerReconciliationTests.certificate
    body=prior.TwoNonceLedgerReconciliationTests.body
    endorse=prior.TwoNonceLedgerReconciliationTests.endorse
    bundle=prior.TwoNonceLedgerReconciliationTests.bundle
    args=prior.TwoNonceLedgerReconciliationTests.args
    check=prior.TwoNonceLedgerReconciliationTests.check
    create=prior.TwoNonceLedgerReconciliationTests.create
    inspect=prior.TwoNonceLedgerReconciliationTests.inspect
    arguments=prior.TwoNonceLedgerReconciliationTests.arguments
    copy_args=prior.TwoNonceLedgerReconciliationTests.copy_args
    clone=prior.TwoNonceLedgerReconciliationTests.clone
    signed_body=prior.TwoNonceLedgerReconciliationTests.signed_body
    sign_receipt=prior.TwoNonceLedgerReconciliationTests.sign_receipt
    params=prior.TwoNonceLedgerReconciliationTests.params
    verify=prior.TwoNonceLedgerReconciliationTests.verify
    attest=prior.TwoNonceLedgerReconciliationTests.attest
    operator_args=prior.TwoNonceLedgerReconciliationTests.operator_args
    make_fields=prior.TwoNonceLedgerReconciliationTests.make_fields
    reserve=prior.TwoNonceLedgerReconciliationTests.reserve
    sign_one=prior.TwoNonceLedgerReconciliationTests.sign_one
    kwargs=prior.TwoNonceLedgerReconciliationTests.kwargs
    crosscheck=prior.TwoNonceLedgerReconciliationTests.crosscheck
    write=prior.TwoNonceLedgerReconciliationTests.write

    def setUp(self):
        prior.TwoNonceLedgerReconciliationTests.setUp(self)
        self.witness_path=Path(self.temp.name)/'private-divergent-histories.json'
        self.write(self.registry_path)
        self.write(self.secondary,nonce_value='d'*32)
        self.trust=dict(
            expected_scope=self.scope,
            external_primary_genesis=self.registry_genesis,
            external_secondary_genesis=self.registry_genesis,
            external_primary_head=ledger.snapshot(
                self.registry_path)['latest_ledger_sha256'],
            external_secondary_head=ledger.snapshot(
                self.secondary)['latest_ledger_sha256'])

    def create_witness(self,**overrides):
        kw=dict(self.trust)
        kw.update(overrides)
        return witness.create(self.witness_path,self.registry_path,
                              self.secondary,**kw)

    def inspect_witness(self,*,archive_pin=None,**overrides):
        kw=dict(self.trust)
        kw.update(overrides)
        pin=hashlib.sha256(self.witness_path.read_bytes()).hexdigest() if archive_pin is None else archive_pin
        return witness.inspect(self.witness_path,
                               external_archive_pin=pin,**kw)

    def test_create_and_offline_replay_two_conflicting_full_chains(self):
        r=self.create_witness()
        self.assertEqual(r['conflict_class'],'forked_hash_chains')
        self.assertEqual(r['common_verified_event_count'],0)
        self.assertEqual(r['primary_verified_events'],1)
        self.assertEqual(r['secondary_verified_events'],1)
        self.assertTrue(r['detached_full_nonce_histories_replayed'])
        self.assertTrue(r['archive_exclusive_no_replace_creation_verified'])
        self.assertEqual(self.witness_path.stat().st_mode&0o777,0o600)

    def test_offline_replay_without_original_source_databases(self):
        created=self.create_witness()
        self.registry_path.unlink()
        self.secondary.unlink()
        r=self.inspect_witness(archive_pin=created['archive_sha256'])
        self.assertEqual(r['conflict_class'],'forked_hash_chains')
        self.assertFalse(r['archive_exclusive_no_replace_creation_verified'])

    def test_create_is_no_overwrite_after_success(self):
        r=self.create_witness()
        raw=self.witness_path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create_witness()
        self.assertEqual(self.witness_path.read_bytes(),raw)
        self.assertEqual(self.inspect_witness()['archive_sha256'],r['archive_sha256'])

    def test_missing_source_without_independent_archive_refused(self):
        self.registry_path.unlink()
        with self.assertRaises((ValueError,OSError)):
            self.create_witness()
        self.assertFalse(self.witness_path.exists())

    def test_missing_witness_archive_detected(self):
        self.create_witness()
        self.witness_path.unlink()
        with self.assertRaises((OSError,ValueError)):
            self.inspect_witness(archive_pin='f'*64)

    def test_changed_archive_bytes_rejected_by_external_pin(self):
        saved=self.create_witness()
        self.witness_path.write_bytes(self.witness_path.read_bytes()+b' ')
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness(archive_pin=saved['archive_sha256'])

    def test_invalid_private_genesis_pin_refused_before_create(self):
        with self.assertRaises((ValueError,witness.DetachedHistoryConflict)):
            self.create_witness(external_primary_genesis='f'*64)
        self.assertFalse(self.witness_path.exists())

    def test_invalid_current_registry_pin_refused_before_create(self):
        with self.assertRaises((witness.DetachedHistoryConflict,
                                cross.LedgerDivergence)):
            self.create_witness(external_secondary_head='f'*64)
        self.assertFalse(self.witness_path.exists())

    def test_inspect_wrong_external_primary_head_rejected(self):
        self.create_witness()
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness(external_primary_head='f'*64)

    def test_inspect_wrong_external_secondary_genesis_rejected(self):
        self.create_witness()
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness(external_secondary_genesis='f'*64)

    def test_identical_histories_cannot_be_archived_as_divergence(self):
        shutil.copyfile(self.registry_path,self.secondary)
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.create_witness(external_secondary_head=
                self.trust['external_primary_head'])
        self.assertFalse(self.witness_path.exists())

    def test_strict_prefix_lag_can_be_archived_and_replayed(self):
        self.secondary.unlink()
        ledger.init(self.secondary,scope=self.scope,
            enrollment=self.registry_enrollment,
            independent_genesis_pin=self.registry_genesis)
        r=self.create_witness(external_secondary_head=self.registry_genesis)
        self.assertEqual(r['conflict_class'],'strict_prefix_lag')
        self.assertEqual(r['common_verified_event_count'],0)

    def test_cross_role_duplicate_nonce_evidence_is_reproduced(self):
        self.secondary.unlink()
        ledger.init(self.secondary,scope=self.scope,
            enrollment=self.registry_enrollment,
            independent_genesis_pin=self.registry_genesis)
        self.write(self.secondary,role_idx=1,nonce_value=self.nonces[0])
        r=self.create_witness(external_secondary_head=
            ledger.snapshot(self.secondary)['latest_ledger_sha256'])
        self.assertTrue(r['cross_registry_duplicate_nonce_with_different_claims_detected'])

    def test_noncanonical_archive_refused_even_if_locally_rehashed(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        self.witness_path.write_bytes(json.dumps(obj,indent=2,sort_keys=True).encode())
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_duplicate_json_fields_refused_even_if_archive_rehashed(self):
        self.create_witness()
        raw=self.witness_path.read_bytes()
        self.witness_path.write_bytes(raw[:-1]+b',"schema":"dupe"}')
        with self.assertRaises(ValueError):
            self.inspect_witness()

    def test_chain_tamper_detected_after_external_archive_pin_recomputed(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        obj['primary']['events'][0][3]='c'*32
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(ValueError):
            self.inspect_witness()

    def test_enrollment_tamper_detected_after_self_pinning(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        obj['primary']['enrollment']['operator-a']['operator_id']='new-operator'
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_invented_history_head_cannot_match_external_pin(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        obj['secondary_head_sha256']='f'*64
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_event_boolean_integer_smuggling_rejected(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        obj['primary']['events'][0][4]=True
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_incomplete_snapshot_schema_rejected(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        del obj['primary']['events']
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_missing_event_cannot_be_accepted_with_old_latest_pin(self):
        self.create_witness()
        obj=json.loads(self.witness_path.read_bytes())
        obj['primary']['events']=[]
        self.witness_path.write_bytes(_canonical(obj))
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_archive_symlink_rejected(self):
        self.create_witness()
        alias=Path(self.temp.name)/'alias-witness.json'
        alias.symlink_to(self.witness_path)
        with self.assertRaises((ValueError,OSError)):
            witness.inspect(alias,
                external_archive_pin=hashlib.sha256(
                    self.witness_path.read_bytes()).hexdigest(),**self.trust)

    def test_archive_hardlink_rejected(self):
        self.create_witness()
        alias=Path(self.temp.name)/'hardlink-witness.json'
        os.link(self.witness_path,alias)
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_archive_world_readable_rejected(self):
        self.create_witness()
        self.witness_path.chmod(0o644)
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness()

    def test_wrong_scope_refused(self):
        self.create_witness()
        with self.assertRaises(witness.DetachedHistoryConflict):
            self.inspect_witness(expected_scope='untrusted-scope')

    def test_report_never_claims_global_cas_or_release(self):
        report=self.create_witness()
        for key in (
            'independently_stored_archive_pin_proved',
            'independent_offhost_evidence_custody_proved',
            'true_global_nonce_cas_consensus_proved',
            'either_signed_receipt_was_physically_stored_proved',
            'automatic_ledger_merge_authorized','automatic_cas_retry_authorized',
            'witness_fence_retirement_authorized','witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(report[key])

    def argv(self,action='create'):
        args=[action,str(self.witness_path),
              '--scope',self.scope,
              '--primary-genesis-pin',self.registry_genesis,
              '--secondary-genesis-pin',self.registry_genesis,
              '--primary-head-pin',self.trust['external_primary_head'],
              '--secondary-head-pin',self.trust['external_secondary_head']]
        if action=='create':
            args.extend(['--primary-registry',str(self.registry_path),
                         '--secondary-registry',str(self.secondary)])
        return args

    def test_cli_create_and_inspect_redacted(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=witness.main(self.argv())
        self.assertEqual(status,0,out.getvalue())
        result=json.loads(out.getvalue())
        with contextlib.redirect_stdout(inspected:=io.StringIO()):
            status=witness.main(self.argv('inspect')+
                ['--archive-pin',result['archive_sha256']])
        self.assertEqual(status,0,inspected.getvalue())
        self.assertTrue(json.loads(inspected.getvalue())[
            'detached_full_nonce_histories_replayed'])
        self.assertNotIn(self.nonces[0],out.getvalue())
        self.assertNotIn(self.nonces[0],inspected.getvalue())

    def test_cli_missing_external_archive_pin_fails_closed(self):
        self.create_witness()
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=witness.main(self.argv('inspect'))
        self.assertEqual(status,1)
        self.assertTrue(json.loads(out.getvalue())['detached_history_evidence_conflict'])
        self.assertFalse(json.loads(out.getvalue())['witness_fence_retired'])

    def test_cli_wrong_pinned_source_fails_without_file_creation(self):
        argv=self.argv()
        argv[argv.index('--secondary-head-pin')+1]='f'*64
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=witness.main(argv)
        self.assertEqual(status,1)
        self.assertFalse(self.witness_path.exists())
        self.assertNotIn(self.nonces[0],out.getvalue())


if __name__=='__main__':
    unittest.main()
