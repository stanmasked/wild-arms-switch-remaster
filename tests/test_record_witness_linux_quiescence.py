"""Synthetic Linux cgroup v2 observation; no service or kernel controls changed."""
import json
import os
import sqlite3
import unittest

from tests import test_record_witness_fence_quiescence as fixture_module
from tools.audit_record_anchor_handoff import _canonical
from tools.audit_record_witness_fence_quiescence import STOP_SCHEMA, STOP_DOMAIN
from tools.audit_record_witness_fence_reconciliation import _sign
from tools.audit_record_witness_linux_quiescence import (
    QuiescenceConflict, observe, verify, evidence_sha256, _scope,
)

BOOT = '11111111-2222-3333-4444-555555555555'
NONCE = '6'*32
SCOPE = 'system.slice/custodian.service'


class LinuxCgroupObservationTests(unittest.TestCase):
    setUp = fixture_module.QuiescencePreflightTests.setUp
    path = fixture_module.QuiescencePreflightTests.path
    request = fixture_module.QuiescencePreflightTests.request
    new_offer = fixture_module.QuiescencePreflightTests.new_offer
    make_offer_and_deposit = (
        fixture_module.QuiescencePreflightTests.make_offer_and_deposit)
    stop = fixture_module.QuiescencePreflightTests.stop

    @classmethod
    def setUpClass(cls):
        fixture_module.QuiescencePreflightTests.setUpClass()
        for name in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, name,
                    getattr(fixture_module.QuiescencePreflightTests, name))

    @classmethod
    def tearDownClass(cls):
        fixture_module.QuiescencePreflightTests.tearDownClass()

    def make_cgroup(self):
        self.root = self.v/'fake-cgroup-v2'
        self.root.mkdir(mode=0o700)
        self.scope_path = self.root/'system.slice'/'custodian.service'
        self.scope_path.mkdir(parents=True)
        self.boot_path = self.v/'fake-boot-id'
        self.boot_path.write_text(BOOT+'\n')
        self.write_controls(self.scope_path)
        st = self.scope_path.stat()
        self.pin = (st.st_dev, st.st_ino)

    def write_controls(self, scope, *, frozen=True, populated=False,
                       procs='', threads=''):
        (scope/'cgroup.events').write_text(
            f'populated {int(populated)}\nfrozen {int(frozen)}\n')
        (scope/'cgroup.freeze').write_text('1\n' if frozen else '0\n')
        (scope/'cgroup.procs').write_text(procs)
        (scope/'cgroup.threads').write_text(threads)

    def snapshot(self, raw, nonce=NONCE, scope=SCOPE, *,
                 device=None, inode=None):
        return observe(
            raw, nonce, scope, BOOT,
            self.pin[0] if device is None else device,
            self.pin[1] if inode is None else inode,
            cgroup_root=self.root, boot_id_path=self.boot_path)

    def signed_stop_for(self, original, observation, *, nonce=NONCE,
                        overrides=None):
        signed, public, pin = self.stop(original)
        body = json.loads(signed)['body']
        body['control_evidence_sha256'] = evidence_sha256(observation)
        body['stop_session_nonce'] = nonce
        body.update(overrides or {})
        output = self.path('linux-signed-stop-')
        _sign(body, STOP_SCHEMA, STOP_DOMAIN, self.admins[0][1], output)
        return output.read_bytes(), public, pin

    def verified(self, original, observation, signed=None):
        raw, pub, pin = signed if signed is not None else (
            self.signed_stop_for(original, observation))
        return verify(
            original, raw, _canonical(observation), pub, pin,
            supervisor_tag='independent-supervisor',
            expected_scope=SCOPE, pinned_boot_id=BOOT,
            pinned_device=self.pin[0], pinned_inode=self.pin[1],
            cgroup_root=self.root, boot_id_path=self.boot_path)

    def test_frozen_empty_exact_cgroup_binds_signed_claim_only(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        report = self.verified(original, observation)
        self.assertTrue(report['signed_supervisor_claim_binds_observed_cgroup'])
        self.assertTrue(report['frozen_and_empty_at_observation'])
        self.assertFalse(report['external_writer_revocation_proved'])
        self.assertFalse(report['witness_fence_retirement_authorized'])

    def test_unfrozen_or_populated_cgroup_fails_closed(self):
        self.make_cgroup()
        original = self.request()
        self.write_controls(self.scope_path, frozen=False)
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original)
        self.write_controls(self.scope_path, populated=True)
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original)

    def test_live_process_and_thread_both_refused(self):
        self.make_cgroup()
        original = self.request()
        self.write_controls(self.scope_path, procs='1234\n')
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original)
        self.write_controls(self.scope_path, threads='4321\n')
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original)

    def test_child_cgroup_population_refused(self):
        self.make_cgroup()
        child = self.scope_path/'nested.scope'
        child.mkdir()
        self.write_controls(child, populated=True)
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(self.request())

    def test_new_child_after_snapshot_invalidates_signed_binding(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        signed = self.signed_stop_for(original, observation)
        child = self.scope_path/'new.scope'
        child.mkdir()
        self.write_controls(child)
        with self.assertRaises(QuiescenceConflict):
            self.verified(original, observation, signed)

    def test_changed_boot_id_and_cgroup_inode_refused(self):
        self.make_cgroup()
        original = self.request()
        self.boot_path.write_text('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n')
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original)
        self.boot_path.write_text(BOOT+'\n')
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(original, inode=self.pin[1]+1)

    def test_changed_evidence_after_signature_refused(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        signed = self.signed_stop_for(original, observation)
        forged = dict(observation)
        forged['boot_id'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        with self.assertRaises(QuiescenceConflict):
            self.verified(original, forged, signed)

    def test_wrong_nonce_and_wrong_request_refused(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        signed = self.signed_stop_for(original, observation, nonce='8'*32)
        with self.assertRaises(QuiescenceConflict):
            self.verified(original, observation, signed)
        signed = self.signed_stop_for(original, observation)
        changed = self.request(nonce='9'*32)
        with self.assertRaises(ValueError):
            self.verified(changed, observation, signed)

    def test_false_supervisor_claim_refused_even_with_empty_cgroup(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        signed = self.signed_stop_for(
            original, observation,
            overrides={'service_restart_blocked': False})
        with self.assertRaises(ValueError):
            self.verified(original, observation, signed)

    def test_symlink_directory_refused(self):
        self.make_cgroup()
        external = self.v/'external-directory'
        external.mkdir()
        (self.scope_path/'escape.scope').symlink_to(external,
                                                    target_is_directory=True)
        with self.assertRaises(QuiescenceConflict):
            self.snapshot(self.request())

    def test_invalid_scope_components_refused(self):
        for scope in ('', '../evil', '/absolute', 'system.slice/../../escape',
                      'system.slice//service', 'system.slice/./service'):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    _scope(scope)

    def test_noncanonical_evidence_rejected(self):
        self.make_cgroup()
        original = self.request()
        observation = self.snapshot(original)
        signed, public, pin = self.signed_stop_for(original, observation)
        with self.assertRaises(ValueError):
            verify(
                original, signed,
                json.dumps(observation).encode(), public, pin,
                supervisor_tag='independent-supervisor',
                expected_scope=SCOPE, pinned_boot_id=BOOT,
                pinned_device=self.pin[0], pinned_inode=self.pin[1],
                cgroup_root=self.root, boot_id_path=self.boot_path)


if __name__ == '__main__':
    unittest.main()
