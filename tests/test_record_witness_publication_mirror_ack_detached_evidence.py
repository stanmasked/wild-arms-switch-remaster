"""Stage 264U: offline complete private signed-ack histories and authentic replay."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import unittest
import shutil

from tests import test_record_witness_publication_mirror_ack_registry_binding as base
from tools import audit_record_witness_publication_mirror_ack_detached_evidence as archive
from tools import audit_record_witness_publication_mirror_ack_registry_binding as bound
from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
from tools import audit_record_witness_publication_receipt_nonce_reconciliation as cross
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_anchor_handoff import _canonical

FAIL=(ValueError,OSError,IndexError,KeyError,TypeError,cross.LedgerDivergence,
      cas.CheckpointCASConflict)


class DetachedMirrorAckEvidenceTests(unittest.TestCase):
    setUpClass=base.MirrorAcknowledgmentRegistryBindingTests.__dict__['setUpClass']
    tearDownClass=base.MirrorAcknowledgmentRegistryBindingTests.__dict__['tearDownClass']

    def setUp(self):
        base.MirrorAcknowledgmentRegistryBindingTests.setUp(self)
        self.archive_path=Path(self.temp.name)/'detached-mirror-ack-evidence.json'
        self.issue_ack()
        self.mirror_acks()

    def context(self):
        return dict(scope=self.scope,genesis_a=self.ack_genesis,
            genesis_b=self.ack_genesis,
            head_a=ledger.snapshot(self.ack_registry)['latest_ledger_sha256'],
            head_b=ledger.snapshot(self.secondary_ack)['latest_ledger_sha256'],
            operator_a_public=self.observers[0][1],
            operator_b_public=self.observers[1][1])

    def make_archive(self,**changes):
        data=dict(self.context())
        data.update(changes)
        return archive.create(self.archive_path,self.ack_registry,
                              self.secondary_ack,
                              signed_envelopes=self.attestations,**data)

    def verify_archive(self,*,archive_pin=None,**changed):
        kw=self.context()
        kw.update(changed)
        pin=(hashlib.sha256(self.archive_path.read_bytes()).hexdigest()
             if archive_pin is None else archive_pin)
        return archive.inspect(self.archive_path,archive_pin=pin,**kw)

    def alter_archive(self,modify):
        data=json.loads(self.archive_path.read_bytes())
        modify(data)
        self.archive_path.write_bytes(_canonical(data))
        return hashlib.sha256(self.archive_path.read_bytes()).hexdigest()

    def test_create_and_replay_two_identical_signed_history_copies(self):
        created=self.make_archive()
        self.assertEqual(created['completed_signed_acknowledgment_count'],1)
        self.assertEqual(created['verified_event_count'],2)
        self.assertTrue(created['full_detached_event_chains_replayed_in_memory'])
        self.assertTrue(created['exclusive_archive_creation_and_readback_verified'])
        self.assertEqual(self.archive_path.stat().st_mode&0o777,0o600)

    def test_inspect_without_original_sqlite_sources(self):
        saved=self.make_archive()
        independent_pins=self.context()
        self.ack_registry.unlink()
        self.secondary_ack.unlink()
        self.guard_path.unlink()
        self.mirror.unlink()
        review=archive.inspect(
            self.archive_path,
            archive_pin=saved['private_evidence_archive_sha256'],
            **independent_pins)
        self.assertEqual(review['completed_signed_acknowledgment_count'],1)
        self.assertFalse(review['actual_source_mirror_inspections_replayed_proved'])
        self.assertFalse(review['exclusive_archive_creation_and_readback_verified'])

    def test_two_distinct_role_signed_envelopes_replay(self):
        self.issue_ack(1)
        self.mirror_acks()
        r=self.make_archive()
        self.assertEqual(r['completed_signed_acknowledgment_count'],2)
        self.assertEqual(r['verified_event_count'],4)

    def test_pending_signature_does_not_become_completed(self):
        from tools import audit_record_witness_publication_receipt_nonce_ledger as ledger
        head=ledger.snapshot(self.ack_registry)['latest_ledger_sha256']
        ledger._record(self.ack_registry,action='reserve',
            expected_head=head,scope=self.scope,role='operator-b',
            operator_id=self.ack_enrollment['operator-b']['operator_id'],
            storage_id=self.stores[1],
            operator_public_pin=self.observers[1][2],
            nonce='c'*32,seq=1,previous=self.previous[1],
            archive_pin='f'*64,evidence_pin='e'*64)
        self.mirror_acks()
        r=self.make_archive()
        self.assertEqual(r['completed_signed_acknowledgment_count'],1)
        self.assertEqual(r['pending_operator_roles'],['operator-b'])

    def test_no_overwrite_of_existing_private_archive(self):
        first=self.make_archive()
        before=self.archive_path.read_bytes()
        with self.assertRaises((FileExistsError,OSError)):
            self.make_archive()
        self.assertEqual(self.archive_path.read_bytes(),before)
        self.assertEqual(self.verify_archive()['private_evidence_archive_sha256'],
                         first['private_evidence_archive_sha256'])

    def test_missing_source_is_not_silently_initialized(self):
        self.ack_registry.unlink()
        with self.assertRaises(FAIL):
            self.make_archive()
        self.assertFalse(self.archive_path.exists())

    def test_missing_secondary_source_is_not_accepted(self):
        self.secondary_ack.unlink()
        with self.assertRaises(FAIL):
            self.make_archive()
        self.assertFalse(self.archive_path.exists())

    def test_two_valid_but_forked_registries_cannot_create_archive(self):
        # Both heads are individually valid; only the cross-registry
        # equality comparison catches this post-copy reservation fork.
        head=ledger.snapshot(self.secondary_ack)['latest_ledger_sha256']
        ledger._record(self.secondary_ack,action='reserve',
            expected_head=head,scope=self.scope,role='operator-b',
            operator_id=self.ack_enrollment['operator-b']['operator_id'],
            storage_id=self.stores[1],
            operator_public_pin=self.observers[1][2],
            nonce='e'*32,seq=1,previous=self.previous[1],
            archive_pin='f'*64,evidence_pin='e'*64)
        with self.assertRaises(FAIL):
            self.make_archive()
        self.assertFalse(self.archive_path.exists())

    def test_missing_independent_archive_pin_refused(self):
        self.make_archive()
        with self.assertRaises(FAIL):
            self.verify_archive(archive_pin='f'*64)

    def test_wrong_secondary_trust_head_refused(self):
        self.make_archive()
        with self.assertRaises(FAIL):
            self.verify_archive(head_b='f'*64)

    def test_wrong_genesis_refused(self):
        self.make_archive()
        with self.assertRaises(FAIL):
            self.verify_archive(genesis_a='f'*64)

    def test_wrong_scope_refused(self):
        self.make_archive()
        with self.assertRaises(FAIL):
            self.verify_archive(scope='untrusted-scope')

    def test_untrusted_operator_pem_refused(self):
        self.make_archive()
        with self.assertRaises(FAIL):
            self.verify_archive(operator_a_public=self.observers[1][1])

    def test_noncanonical_json_refused_even_with_new_self_pin(self):
        self.make_archive()
        self.archive_path.write_bytes(
            json.dumps(json.loads(self.archive_path.read_bytes()),indent=2).encode())
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_duplicate_schema_fields_refused(self):
        self.make_archive()
        raw=self.archive_path.read_bytes()
        self.archive_path.write_bytes(raw[:-1]+b',"schema":"another"}')
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_missing_enrollment_refused(self):
        self.make_archive()
        self.alter_archive(lambda obj:obj['primary'].pop('enrollment'))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_wrong_claimed_complete_signed_count_not_possible(self):
        self.make_archive()
        self.alter_archive(lambda obj:obj['primary']['events'].pop())
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_modified_hash_chain_with_updated_self_pin_refused(self):
        self.make_archive()
        self.alter_archive(lambda obj:obj['primary']['events'][0].__setitem__(3,'e'*32))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_changed_envelope_bytes_refused_after_archive_rehashed(self):
        self.make_archive()
        def mutate(o):
            entry=o['envelopes']['operator-a'][0]
            raw=base64.b64decode(entry['raw_base64'])
            entry['raw_base64']=base64.b64encode(raw+b' ').decode('ascii')
        self.alter_archive(mutate)
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_changed_envelope_sha256_refused(self):
        self.make_archive()
        self.alter_archive(lambda o:o['envelopes']['operator-a'][0].__setitem__(
            'sha256','f'*64))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_injected_extra_signed_envelope_refused(self):
        self.make_archive()
        self.alter_archive(lambda o:o['envelopes']['operator-a'].append(
            dict(o['envelopes']['operator-a'][0])))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_missing_original_signed_envelope_refused(self):
        self.make_archive()
        self.alter_archive(lambda o:o['envelopes']['operator-a'].clear())
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_unknown_schema_fields_refused(self):
        self.make_archive()
        self.alter_archive(lambda o:o.__setitem__('unexpected',True))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_boolean_sequence_smuggling_refused(self):
        self.make_archive()
        self.alter_archive(lambda o:o['primary']['events'][0].__setitem__(4,True))
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_private_archive_symlink_rejected(self):
        saved=self.make_archive()
        alias=Path(self.temp.name)/'sym-evidence.json'
        alias.symlink_to(self.archive_path)
        with self.assertRaises(FAIL):
            archive.inspect(alias,archive_pin=saved['private_evidence_archive_sha256'],
                **self.context())

    def test_private_archive_hardlink_rejected(self):
        self.make_archive()
        alias=Path(self.temp.name)/'hard-evidence.json'
        os.link(self.archive_path,alias)
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_publicly_readable_archive_rejected(self):
        self.make_archive()
        self.archive_path.chmod(0o644)
        with self.assertRaises(FAIL):
            self.verify_archive()

    def test_report_does_not_claim_offhost_or_release(self):
        report=self.make_archive()
        for name in (
            'independent_external_archive_sha256_retention_proved',
            'physically_independent_operator_custody_proved',
            'actual_source_mirror_inspections_replayed_proved',
            'global_nonce_cas_consensus_proved',
            'automatic_ledger_merge_authorized',
            'automatic_pending_recovery_authorized',
            'automatic_cas_retry_authorized',
            'witness_fence_retirement_authorized',
            'witness_fence_retired',
            'native_switch_game_build_verified'):
            self.assertFalse(report[name],name)

    def cli_arguments(self,action):
        opts=self.context()
        args=[action,str(self.archive_path),
              '--scope',opts['scope'],
              '--genesis-a',opts['genesis_a'],
              '--genesis-b',opts['genesis_b'],
              '--head-a',opts['head_a'],'--head-b',opts['head_b'],
              '--operator-a-public',str(opts['operator_a_public']),
              '--operator-b-public',str(opts['operator_b_public'])]
        if action=='create':
            self.write_manifest()
            args.extend(['--primary',str(self.ack_registry),
                         '--secondary',str(self.secondary_ack),
                         '--private-signed-manifest',str(self.manifest_acks)])
        else:
            args.extend(['--archive-pin',
                         hashlib.sha256(self.archive_path.read_bytes()).hexdigest()])
        return args

    def test_cli_create_and_detached_inspect(self):
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=archive.main(self.cli_arguments('create'))
        self.assertEqual(code,0,out.getvalue())
        independently_pinned_cli=self.cli_arguments('inspect')
        self.ack_registry.unlink()
        self.secondary_ack.unlink()
        with contextlib.redirect_stdout(checked:=io.StringIO()):
            code=archive.main(independently_pinned_cli)
        self.assertEqual(code,0,checked.getvalue())
        self.assertTrue(json.loads(checked.getvalue())[
            'every_completed_attestation_signature_reverified_offline'])
        self.assertNotIn(self.nonces[0],checked.getvalue())

    def test_cli_requires_external_archive_pin(self):
        self.make_archive()
        args=self.cli_arguments('inspect')
        idx=args.index('--archive-pin')
        args=args[:idx]+args[idx+2:]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            code=archive.main(args)
        self.assertEqual(code,1)
        self.assertTrue(json.loads(out.getvalue())[
            'detached_signed_mirror_evidence_conflict'])


for name in (
    'sign','compute_pin','fetch','_advanced_keeper','certificate','body',
    'endorse','bundle','args','check','create','inspect','arguments',
    'copy_args','clone','signed_body','sign_receipt','operator_args',
    'make_fields','reserve','sign_one','kwargs','crosscheck','write',
    'create_witness','inspect_witness','trusted','body_for','make_signed',
    'checked','issue','guarded','snapshot','advance','seal_mirror',
    'params','check_mirror','one_complete','build_manifest',
    'expected_ack_body','signed_ack','verify','ack_arguments',
    'sign_guarded_ack','ack_snapshot',
    'issue_ack','mirror_acks','trusted_acks','audit_acks','prepare_first_ack',
    'write_manifest'
):
    if hasattr(base.MirrorAcknowledgmentRegistryBindingTests,name):
        setattr(DetachedMirrorAckEvidenceTests,name,
                getattr(base.MirrorAcknowledgmentRegistryBindingTests,name))

if __name__=='__main__':
    unittest.main()
