"""Stage 263O: three-operator signed registry escrow and equivocation tests."""
import contextlib
import hashlib
import io
import json
import sqlite3
import unittest

from tests import test_record_witness_checkpoint_registry as previous
from tools import audit_record_witness_escrow_quorum as escrow
from tools import audit_record_witness_checkpoint_registry as registry
from tools import audit_record_witness_replay_head_checkpoint as checkpoint
from tools.audit_record_witness_fence_reconciliation import _sign


TAG = 'private-wild-arms-ledger'
NONCE = 'b'*32


class ThreeOperatorEscrowTests(unittest.TestCase):
    setUp = previous.AcceptedCheckpointRegistryTests.setUp
    path = previous.AcceptedCheckpointRegistryTests.path
    request = previous.AcceptedCheckpointRegistryTests.request
    stop = previous.AcceptedCheckpointRegistryTests.stop
    make_cgroup = previous.AcceptedCheckpointRegistryTests.make_cgroup
    write_controls = previous.AcceptedCheckpointRegistryTests.write_controls
    snapshot = previous.AcceptedCheckpointRegistryTests.snapshot
    signed_stop_for = previous.AcceptedCheckpointRegistryTests.signed_stop_for
    new_offer = previous.AcceptedCheckpointRegistryTests.new_offer
    make_offer_and_deposit = previous.AcceptedCheckpointRegistryTests.make_offer_and_deposit
    init_capture = previous.AcceptedCheckpointRegistryTests.init_capture
    build = previous.AcceptedCheckpointRegistryTests.build
    prepare = previous.AcceptedCheckpointRegistryTests.prepare
    init_journal = previous.AcceptedCheckpointRegistryTests.init_journal
    enroll = previous.AcceptedCheckpointRegistryTests.enroll
    second_bundle = previous.AcceptedCheckpointRegistryTests.second_bundle
    sign_heads = previous.AcceptedCheckpointRegistryTests.sign_heads
    fresh = previous.AcceptedCheckpointRegistryTests.fresh
    first_candidate = previous.AcceptedCheckpointRegistryTests.first_candidate
    accept = previous.AcceptedCheckpointRegistryTests.accept

    @classmethod
    def setUpClass(cls):
        previous.AcceptedCheckpointRegistryTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls, name,
                    getattr(previous.AcceptedCheckpointRegistryTests,name))

    @classmethod
    def tearDownClass(cls):
        previous.AcceptedCheckpointRegistryTests.tearDownClass()

    def signed_round(self, *, count=None, registry_head=None,
                     checkpoint_head=None, prior=escrow.ESCROW_GENESIS,
                     nonce=NONCE, tag=TAG, changed=None):
        count = self.rcount if count is None else count
        registry_head = self.rhead if registry_head is None else registry_head
        checkpoint_head = (self.rcheckpoint if checkpoint_head is None
                           else checkpoint_head)
        self.signed = {}
        self.signed_paths = {}
        self.keys = {}
        self.pins = {}
        changed = changed or {}
        for i, role in enumerate(escrow.ROLES):
            key = self.admins[i]
            body = escrow.make_body(
                role, count, registry_head, checkpoint_head, prior, nonce, tag)
            body.update(changed.get(role, {}))
            path = self.path('escrow-signed-'+role+'-')
            _sign(body, escrow.SCHEMA, escrow.DOMAIN, key[1], path)
            self.signed[role] = path.read_bytes()
            self.signed_paths[role] = path
            self.keys[role] = key[2]
            self.pins[role] = key[3]
        self.escrow_pin = escrow.bundle_digest(self.signed)
        self.prior = prior

    def check(self, *, signed=None, pins=None, keys=None, bundle_pin=None,
              prior_pin=None, count=None, registry_head=None,
              checkpoint_head=None, tag=TAG):
        return escrow.verify(
            self.registry,
            self.signed if signed is None else signed,
            self.keys if keys is None else keys,
            self.pins if pins is None else pins,
            checkpoint_tag=tag,
            prior_escrow_pin=self.prior if prior_pin is None else prior_pin,
            independently_pinned_bundle=(
                self.escrow_pin if bundle_pin is None else bundle_pin),
            expected_registry_count=(
                self.rcount if count is None else count),
            expected_registry_head=(
                self.rhead if registry_head is None else registry_head),
            expected_latest_checkpoint=(
                self.rcheckpoint if checkpoint_head is None else checkpoint_head))

    def accepted_one(self):
        self.fresh()
        self.first_candidate()
        item = self.accept()
        self.rcount = item['registry_event_count']
        self.rhead = item['registry_head_sha256']
        self.rcheckpoint = item['latest_checkpoint_sha256']

    def test_genesis_unanimous_three_signers_advisory_only(self):
        self.fresh()
        self.signed_round()
        result = self.check()
        self.assertTrue(result['three_distinct_operator_signatures_verified'])
        self.assertTrue(result['all_supplied_operator_receipts_agree'])
        self.assertEqual(result['registry_event_count'], 0)
        self.assertEqual(result['escrow_bundle_sha256'], self.escrow_pin)
        for flag in ('independent_physical_archive_storage_proved',
                     'all_possible_conflicting_receipts_discovered',
                     'historical_replay_with_old_pins_excluded',
                     'witness_fence_retirement_authorized',
                     'witness_fence_retired'):
            self.assertFalse(result[flag])

    def test_after_accepted_registry_checkpoint_all_three_agree(self):
        self.accepted_one()
        self.signed_round(prior='a'*64)
        result = self.check()
        self.assertEqual(result['registry_event_count'], 1)
        self.assertEqual(result['latest_checkpoint_sha256'],self.rcheckpoint)

    def test_missing_one_operator_receipt_fails_closed(self):
        self.fresh()
        self.signed_round()
        signed = dict(self.signed)
        del signed['escrow-c']
        with self.assertRaises(escrow.EscrowConflict):
            self.check(signed=signed)

    def test_same_key_under_two_roles_refused(self):
        self.fresh()
        self.signed_round()
        same = dict(self.pins, **{'escrow-c':self.pins['escrow-a']})
        keys = dict(self.keys, **{'escrow-c':self.keys['escrow-a']})
        with self.assertRaises(escrow.EscrowConflict):
            self.check(pins=same, keys=keys)

    def test_reformatted_pem_cannot_fake_new_signer(self):
        self.fresh()
        self.signed_round()
        # PEM byte hashes differ, DER public key bytes do not.
        text = self.admins[0][2].read_text()
        lines = text.splitlines()
        lines[1:2] = [lines[1][:12], lines[1][12:]]
        path = self.path('rewrapped-escrow-key-')
        path.write_text('\n'.join(lines)+'\n')
        path.chmod(0o600)
        keys = dict(self.keys)
        pins = dict(self.pins)
        keys['escrow-c'] = path
        pins['escrow-c'] = hashlib.sha256(path.read_bytes()).hexdigest()
        # The old C signature is under a different key, so refusal occurs
        # before identity comparison; a valid spoofed signature is tested next.
        with self.assertRaises(ValueError):
            self.check(keys=keys,pins=pins)
        body = escrow.make_body('escrow-c',0,registry.GENESIS,
                                checkpoint.ANCHOR_GENESIS,
                                escrow.ESCROW_GENESIS,NONCE,TAG)
        signed_c = self.path('rewrapped-signed-c-')
        _sign(body,escrow.SCHEMA,escrow.DOMAIN,self.admins[0][1],signed_c)
        signed = dict(self.signed)
        signed['escrow-c'] = signed_c.read_bytes()
        with self.assertRaises(escrow.EscrowConflict):
            self.check(keys=keys,pins=pins,signed=signed,
                       bundle_pin=escrow.bundle_digest(signed))

    def test_one_operator_signs_conflicting_checkpoint_head(self):
        self.accepted_one()
        self.signed_round(
            prior='a'*64, changed={'escrow-c':
                                   {'latest_checkpoint_sha256':'f'*64}})
        with self.assertRaises(escrow.EscrowConflict):
            self.check()

    def test_conflicting_event_count_between_signers(self):
        self.accepted_one()
        self.signed_round(prior='a'*64,
                          changed={'escrow-b':{'registry_event_count':2}})
        with self.assertRaises(escrow.EscrowConflict):
            self.check()

    def test_round_nonce_mismatch_between_signers(self):
        self.fresh()
        self.signed_round(changed={'escrow-b':
                                  {'escrow_round_nonce':'a'*32}})
        with self.assertRaises(escrow.EscrowConflict):
            self.check()

    def test_external_bundle_pin_cannot_be_self_replaced(self):
        self.fresh()
        self.signed_round()
        with self.assertRaises(escrow.EscrowConflict):
            self.check(bundle_pin='f'*64)

    def test_wrong_prior_escrow_anchor_rejected(self):
        self.accepted_one()
        self.signed_round(prior='a'*64)
        with self.assertRaises(escrow.EscrowConflict):
            self.check(prior_pin='b'*64)

    def test_replay_of_old_receipts_against_new_registry_fails(self):
        self.fresh()
        self.signed_round()
        self.first_candidate()
        self.accept()
        with self.assertRaises(escrow.EscrowConflict):
            self.check()

    def test_old_registry_plus_old_pins_cannot_be_excluded_here(self):
        self.fresh()
        self.signed_round()
        result = self.check()
        self.assertTrue(result['signed_registry_head_matches_current_snapshot'])
        self.assertFalse(result['historical_replay_with_old_pins_excluded'])

    def test_malformed_genesis_prior_cannot_be_signed_successfully(self):
        with self.assertRaises(escrow.EscrowConflict):
            escrow.make_body('escrow-a',0,registry.GENESIS,
                             checkpoint.ANCHOR_GENESIS,
                             'f'*64,NONCE,TAG)

    def test_invalid_role_or_nonce_cannot_pass(self):
        for role,nonce in (('escrow-x',NONCE),('escrow-a','bad')):
            with self.subTest(role=role,nonce=nonce):
                with self.assertRaises(escrow.EscrowConflict):
                    escrow.make_body(role,1,'a'*64,'b'*64,
                                     escrow.ESCROW_GENESIS,nonce,TAG)

    def test_malformed_signature_and_unsafe_claim_refused(self):
        self.fresh()
        self.signed_round()
        signed = dict(self.signed)
        signed['escrow-a'] = signed['escrow-b']
        with self.assertRaises(ValueError):
            self.check(signed=signed)
        self.signed_round(changed={'escrow-c':
                                   {'witness_fence_retirement_authorized':True}})
        with self.assertRaises(escrow.EscrowConflict):
            self.check()

    def test_changed_registry_head_or_external_checkpoint_pin_refused(self):
        self.fresh()
        self.signed_round()
        with self.assertRaises(escrow.EscrowConflict):
            self.check(registry_head='f'*64)
        with self.assertRaises(escrow.EscrowConflict):
            self.check(checkpoint_head='f'*64)

    def test_corrupt_registry_chain_refused_after_authentic_signatures(self):
        self.accepted_one()
        self.signed_round(prior='a'*64)
        with sqlite3.connect(self.registry) as con:
            con.execute(
                'UPDATE accepted_replay_checkpoints SET '
                'event_sha256=? WHERE sequence=1',('f'*64,))
        with self.assertRaises(registry.RegistryConflict):
            self.check()

    def test_cli_redacts_receipts_and_does_not_unlock(self):
        self.fresh()
        self.signed_round()
        args = [
            str(self.registry), '--checkpoint-tag', TAG,
            '--prior-escrow-sha256',self.prior,
            '--latest-escrow-sha256',self.escrow_pin,
            '--expected-count','0',
            '--expected-head',registry.GENESIS,
            '--expected-checkpoint',checkpoint.ANCHOR_GENESIS,
        ]
        for role in escrow.ROLES:
            args.extend(('--'+role+'-signed',str(self.signed_paths[role]),
                         '--'+role+'-public',str(self.keys[role]),
                         '--'+role+'-public-sha256',self.pins[role]))
        with contextlib.redirect_stdout(buffer := io.StringIO()):
            status = escrow.main(args)
        self.assertEqual(status,0,buffer.getvalue())
        result=json.loads(buffer.getvalue())
        self.assertFalse(result['witness_fence_retired'])
        self.assertNotIn('signature_hex',buffer.getvalue())
        self.assertNotIn('escrow_round_nonce',buffer.getvalue())


if __name__ == '__main__':
    unittest.main()
