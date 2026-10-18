"""Stage 264F synthetic Ed25519 fork-evidence archive + retention regressions."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import unittest
from unittest import mock

from tests import test_record_witness_publication_highwater_equivocation as fixture
from tools import audit_record_witness_publication_equivocation_archive as store
from tools import audit_record_witness_publication_highwater_equivocation as ev
from tools import audit_record_witness_publication_checkpoint_cas as cas
from tools.audit_record_anchor_handoff import _canonical


class EvidenceArchiveTests(unittest.TestCase):
    setUpClass=fixture.EquivocationEvidenceTests.__dict__['setUpClass']
    tearDownClass=fixture.EquivocationEvidenceTests.__dict__['tearDownClass']
    sign=fixture.EquivocationEvidenceTests.sign
    compute_pin=fixture.EquivocationEvidenceTests.compute_pin
    fetch=fixture.EquivocationEvidenceTests.fetch
    _advanced_keeper=fixture.EquivocationEvidenceTests._advanced_keeper
    certificate=fixture.EquivocationEvidenceTests.certificate
    body=fixture.EquivocationEvidenceTests.body
    endorse=fixture.EquivocationEvidenceTests.endorse
    bundle=fixture.EquivocationEvidenceTests.bundle
    args=fixture.EquivocationEvidenceTests.args
    check=fixture.EquivocationEvidenceTests.check

    def setUp(self):
        fixture.EquivocationEvidenceTests.setUp(self)
        self.archive=Path(self.temp.name)/'signed-fork-archive.json'
        self.evidence_sha=self.check()['canonical_evidence_sha256']
        self.meta=dict(
            scope=self.scope,
            operator_a_id='offhost-highwater-a',
            operator_b_id='offhost-highwater-b',
            operator_a_pin=self.observers[0][2],
            operator_b_pin=self.observers[1][2],
            parent_old_a_pin=self.pins_a['old_a'],
            parent_old_b_pin=self.pins_a['old_b'],
            previous_transition_bundle_sha256=self.previous,
            expected_parent_generation=self.initial['generation'],
            expected_parent_pair_pin=self.initial['pair_sha256'],
            expected_parent_event_head=self.initial['event_head_sha256'])

    def create(self,**changed):
        args=dict(
            metadata=dict(self.meta),
            expected_evidence_sha256=self.evidence_sha,
            operator_a_public=self.observers[0][1],
            operator_b_public=self.observers[1][1],
            external_operator_a_pin=self.observers[0][2],
            external_operator_b_pin=self.observers[1][2])
        args.update(changed)
        return store.create(self.archive,self.branch_a,self.branch_b,
                            self.pins_a,self.pins_b,**args)

    def inspect(self,**changed):
        args=dict(
            expected_archive_sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            expected_evidence_sha256=self.evidence_sha,
            operator_a_public=self.observers[0][1],
            operator_b_public=self.observers[1][1],
            external_operator_a_pin=self.observers[0][2],
            external_operator_b_pin=self.observers[1][2])
        args.update(changed)
        return store.inspect(self.archive,**args)

    def test_private_archive_creation_readback_and_signatures(self):
        r=self.create()
        self.assertTrue(r['archive_no_replace_creation_and_readback_verified'])
        self.assertTrue(r['archived_sibling_signatures_revalidated'])
        self.assertEqual(r['canonical_evidence_sha256'],self.evidence_sha)
        self.assertEqual(r['archive_sha256'],hashlib.sha256(
            self.archive.read_bytes()).hexdigest())
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode),0o600)
        self.assertFalse(r['witness_fence_retired'])

    def test_separate_readback_against_trusted_archive_hash(self):
        saved=self.create()
        checked=self.inspect(expected_archive_sha256=saved['archive_sha256'])
        self.assertTrue(checked['archive_exact_independently_pinned_readback_verified'])
        self.assertFalse(checked['archive_no_replace_creation_and_readback_verified'])

    def test_existing_archive_never_overwritten(self):
        old=self.create()
        before=self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(self.archive.read_bytes(),before)
        self.assertEqual(self.inspect()['archive_sha256'],old['archive_sha256'])

    def test_second_conflicting_archive_cannot_replace_first(self):
        self.create()
        before=self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create(expected_evidence_sha256=self.evidence_sha)
        self.assertEqual(self.archive.read_bytes(),before)

    def test_external_archive_hash_mismatch_rejected(self):
        self.create()
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect(expected_archive_sha256='f'*64)

    def test_external_evidence_digest_mismatch_rejected(self):
        self.create()
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect(expected_evidence_sha256='f'*64)

    def test_wrong_external_operator_key_pin_rejected_on_read(self):
        self.create()
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect(external_operator_a_pin='f'*64)

    def test_wrong_signer_public_key_rejected_on_read(self):
        self.create()
        with self.assertRaises(cas.CheckpointCASConflict):
            self.inspect(operator_a_public=self.observers[1][1])

    def test_missing_archive_cannot_be_silently_regenerated(self):
        with self.assertRaises((FileNotFoundError,ValueError)):
            self.inspect(expected_archive_sha256='a'*64)
        self.assertFalse(self.archive.exists())

    def test_deleted_archive_detected_with_old_pin(self):
        saved=self.create()
        self.archive.unlink()
        with self.assertRaises((FileNotFoundError,ValueError)):
            self.inspect(expected_archive_sha256=saved['archive_sha256'])
        self.assertFalse(self.archive.exists())

    def test_truncated_archive_detected(self):
        old=self.create()
        self.archive.write_bytes(self.archive.read_bytes()[:-8])
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect(expected_archive_sha256=old['archive_sha256'])

    def test_modified_archive_detected_by_external_pin(self):
        old=self.create()
        raw=self.archive.read_bytes()
        self.archive.write_bytes(raw.replace(b'"schema":',b'"altered_schema":',1))
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect(expected_archive_sha256=old['archive_sha256'])

    def test_private_archive_permissions_enforced(self):
        self.create()
        self.archive.chmod(0o644)
        with self.assertRaises(ValueError):
            self.inspect()

    def test_archive_symlink_rejected(self):
        self.create()
        alias=Path(self.temp.name)/'alias.json'
        alias.symlink_to(self.archive)
        with self.assertRaises(store.EvidenceArchiveConflict):
            store.inspect(alias,expected_archive_sha256=hashlib.sha256(
                self.archive.read_bytes()).hexdigest(),
                expected_evidence_sha256=self.evidence_sha,
                operator_a_public=self.observers[0][1],
                operator_b_public=self.observers[1][1],
                external_operator_a_pin=self.observers[0][2],
                external_operator_b_pin=self.observers[1][2])

    def test_archive_hardlink_rejected_when_link_count_check_active(self):
        self.create()
        alias=Path(self.temp.name)/'hardlink.json'
        os.link(self.archive,alias)
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect()

    def test_archive_parent_world_readable_rejected(self):
        self.create()
        parent=self.archive.parent
        parent.chmod(0o755)
        self.addCleanup(parent.chmod,0o700)
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect()

    def test_noncanonical_archive_json_rejected_even_if_self_pinned(self):
        self.create()
        obj=json.loads(self.archive.read_bytes())
        raw=json.dumps(obj,indent=2,sort_keys=True).encode()
        self.archive.write_bytes(raw)
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect()

    def test_duplicate_archive_json_fields_rejected(self):
        self.create()
        raw=self.archive.read_bytes()
        changed=raw[:-1]+b',"schema":"duplicate"}'
        self.archive.write_bytes(changed)
        with self.assertRaises(cas.CheckpointCASConflict):
            self.inspect()

    def test_signed_envelope_tampering_refused_even_with_local_hash_recomputed(self):
        self.create()
        obj=json.loads(self.archive.read_bytes())
        x=obj['branches']['left']['endorsement_a']
        x['envelope_b64']='YQ=='
        x['sha256']=hashlib.sha256(b'a').hexdigest()
        self.archive.write_bytes(_canonical(obj))
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect()

    def test_invalid_base64_refused(self):
        self.create()
        obj=json.loads(self.archive.read_bytes())
        obj['branches']['left']['old_a']['envelope_b64']='%invalid'
        self.archive.write_bytes(_canonical(obj))
        with self.assertRaises(store.EvidenceArchiveConflict):
            self.inspect()

    def test_unsafe_creation_scope_refused_before_file_write(self):
        m=dict(self.meta,scope='bad scope!')
        with self.assertRaises(cas.CheckpointCASConflict):
            self.create(metadata=m)
        self.assertFalse(self.archive.exists())

    def test_wrong_external_evidence_pin_refused_before_file_write(self):
        with self.assertRaises(cas.CheckpointCASConflict):
            self.create(expected_evidence_sha256='f'*64)
        self.assertFalse(self.archive.exists())

    def test_wrong_envelope_sha_refused_before_file_write(self):
        wrong=dict(self.pins_b,new_b='f'*64)
        with self.assertRaises(store.EvidenceArchiveConflict):
            store.create(self.archive,self.branch_a,self.branch_b,
                self.pins_a,wrong,metadata=self.meta,
                expected_evidence_sha256=self.evidence_sha,
                operator_a_public=self.observers[0][1],
                operator_b_public=self.observers[1][1],
                external_operator_a_pin=self.observers[0][2],
                external_operator_b_pin=self.observers[1][2])
        self.assertFalse(self.archive.exists())

    def test_archive_readback_does_not_prove_external_custody(self):
        result=self.create()
        self.assertFalse(result['external_archive_custody_proved'])
        self.assertFalse(result['tamper_or_deletion_prevention_proved'])
        self.assertFalse(result['physical_durability_proved'])
        self.assertFalse(result['either_branch_keeper_commit_proved'])
        self.assertFalse(result['automatic_cas_retry_authorized'])

    def test_overlong_archive_rejected(self):
        self.create()
        self.archive.write_bytes(b'x'*(store.MAX_ARCHIVE+1))
        with self.assertRaises(ValueError):
            self.inspect()

    def test_cli_missing_independent_archive_pin_returns_redacted_conflict(self):
        self.create()
        args=['inspect',str(self.archive),
              '--operator-a-public',str(self.observers[0][1]),
              '--operator-b-public',str(self.observers[1][1]),
              '--operator-a-pin',self.observers[0][2],
              '--operator-b-pin',self.observers[1][2],
              '--evidence-sha256',self.evidence_sha]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=store.main(args)
        self.assertEqual(status,1)
        report=json.loads(out.getvalue())
        self.assertTrue(report['evidence_archive_conflict'])
        self.assertFalse(report['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())

    def test_cli_inspect_with_external_pin_returns_verified_redacted_report(self):
        saved=self.create()
        args=['inspect',str(self.archive),
              '--operator-a-public',str(self.observers[0][1]),
              '--operator-b-public',str(self.observers[1][1]),
              '--operator-a-pin',self.observers[0][2],
              '--operator-b-pin',self.observers[1][2],
              '--evidence-sha256',self.evidence_sha,
              '--expected-archive-sha256',saved['archive_sha256']]
        with contextlib.redirect_stdout(out:=io.StringIO()):
            status=store.main(args)
        self.assertEqual(status,0,out.getvalue())
        result=json.loads(out.getvalue())
        self.assertTrue(result['archived_sibling_signatures_revalidated'])
        self.assertFalse(result['witness_fence_retired'])
        self.assertNotIn('signature_hex',out.getvalue())


if __name__=='__main__':
    unittest.main()
