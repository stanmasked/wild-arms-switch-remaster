"""Stage 263P: synthetic consecutive signed escrow chain / rollback tests."""
import contextlib
import hashlib
import io
import json
import unittest

from tests import test_record_witness_escrow_quorum as fixture
from tools import audit_record_witness_escrow_history as history
from tools import audit_record_witness_escrow_quorum as escrow
from tools import audit_record_witness_checkpoint_registry as registry
from tools import audit_record_witness_replay_head_checkpoint as checkpoint
from tools.audit_record_witness_fence_reconciliation import _sign


class EscrowHistoryTests(unittest.TestCase):
    setUp = fixture.ThreeOperatorEscrowTests.setUp
    path = fixture.ThreeOperatorEscrowTests.path
    request = fixture.ThreeOperatorEscrowTests.request
    stop = fixture.ThreeOperatorEscrowTests.stop
    make_cgroup = fixture.ThreeOperatorEscrowTests.make_cgroup
    write_controls = fixture.ThreeOperatorEscrowTests.write_controls
    snapshot = fixture.ThreeOperatorEscrowTests.snapshot
    signed_stop_for = fixture.ThreeOperatorEscrowTests.signed_stop_for
    new_offer = fixture.ThreeOperatorEscrowTests.new_offer
    make_offer_and_deposit = fixture.ThreeOperatorEscrowTests.make_offer_and_deposit
    init_capture = fixture.ThreeOperatorEscrowTests.init_capture
    build = fixture.ThreeOperatorEscrowTests.build
    prepare = fixture.ThreeOperatorEscrowTests.prepare
    init_journal = fixture.ThreeOperatorEscrowTests.init_journal
    enroll = fixture.ThreeOperatorEscrowTests.enroll
    second_bundle = fixture.ThreeOperatorEscrowTests.second_bundle
    sign_heads = fixture.ThreeOperatorEscrowTests.sign_heads
    fresh = fixture.ThreeOperatorEscrowTests.fresh
    first_candidate = fixture.ThreeOperatorEscrowTests.first_candidate
    accept = fixture.ThreeOperatorEscrowTests.accept
    signed_round = fixture.ThreeOperatorEscrowTests.signed_round

    @classmethod
    def setUpClass(cls):
        fixture.ThreeOperatorEscrowTests.setUpClass()
        for name in ('ca','server_key','server_cert','server_pin',
                     'client_key','client_cert','client_pin',
                     'sign_key','sign_pub','sign_pub_pin'):
            setattr(cls,name,getattr(fixture.ThreeOperatorEscrowTests,name))

    @classmethod
    def tearDownClass(cls):
        fixture.ThreeOperatorEscrowTests.tearDownClass()

    def stage(self, count=1):
        self.fresh()
        self.signed_round()
        genesis = dict(self.escrow_signed)
        genesis_hash = escrow.bundle_digest(genesis)
        self.rounds = [genesis]
        self.latest = genesis_hash
        if count >= 1:
            self.first_candidate()
            accepted = self.accept()
            self.signed_round(
                count=1, registry_head=accepted['registry_head_sha256'],
                checkpoint_head=accepted['latest_checkpoint_sha256'],
                prior=self.latest, nonce='c'*32)
            self.rounds.append(dict(self.escrow_signed))
            self.latest = escrow.bundle_digest(self.rounds[-1])
            self.accepted_first = accepted
            self.current_count = 1
            self.current_head = accepted['registry_head_sha256']
            self.current_checkpoint = accepted['latest_checkpoint_sha256']
        else:
            self.current_count = 0
            self.current_head = registry.GENESIS
            self.current_checkpoint = checkpoint.ANCHOR_GENESIS
        if count >= 2:
            raw,pin,reports,signed = self.second_bundle()
            second_replay = self.enroll(
                composite_raw=raw,composite_pin=pin,reports=reports,
                signed=signed,expected_count=1,
                expected_head=self.replay_first['ledger_head_sha256'])
            self.sign_heads(
                count=2,chain_head=second_replay['ledger_head_sha256'],
                prior=self.current_checkpoint,nonce='2'*32)
            accepted = self.accept(
                count=1,head=self.current_head,
                latest=self.current_checkpoint)
            self.signed_round(
                count=2,registry_head=accepted['registry_head_sha256'],
                checkpoint_head=accepted['latest_checkpoint_sha256'],
                prior=self.latest,nonce='d'*32)
            self.rounds.append(dict(self.escrow_signed))
            self.latest = escrow.bundle_digest(self.rounds[-1])
            self.current_count = 2
            self.current_head = accepted['registry_head_sha256']
            self.current_checkpoint = accepted['latest_checkpoint_sha256']
        self.history_raw = history.pack(self.rounds)
        self.history_pin = hashlib.sha256(self.history_raw).hexdigest()

    def check(self, *, raw=None, pin=None, rounds=None,
              latest=None, count=None, head=None, checkpoint_pin=None,
              public=None, pins=None, comparison=None, comparison_pin=None):
        if rounds is not None:
            raw = history.pack(rounds)
            pin = hashlib.sha256(raw).hexdigest()
        return history.verify(
            self.registry,
            self.history_raw if raw is None else raw,
            self.history_pin if pin is None else pin,
            self.keys if public is None else public,
            self.pins if pins is None else pins,
            checkpoint_tag=fixture.TAG,
            expected_registry_count=self.current_count if count is None else count,
            expected_registry_head=self.current_head if head is None else head,
            expected_latest_checkpoint=(
                self.current_checkpoint if checkpoint_pin is None
                else checkpoint_pin),
            expected_latest_escrow=self.latest if latest is None else latest,
            comparison_raw=comparison,comparison_pin=comparison_pin)

    def test_signed_genesis_only_is_advisory(self):
        self.stage(0)
        result = self.check()
        self.assertEqual(result['signed_rounds'],1)
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['independent_physical_archive_storage_proved'])

    def test_genesis_plus_first_checkpoint_are_contiguous(self):
        self.stage(1)
        report = self.check()
        self.assertEqual(report['signed_rounds'],2)
        self.assertTrue(report['every_accepted_checkpoint_has_exactly_one_archive_round'])
        self.assertEqual(report['latest_escrow_bundle_sha256'],self.latest)

    def test_two_checkpoint_history_is_complete(self):
        self.stage(2)
        report = self.check()
        self.assertEqual(report['registry_event_count'],2)
        self.assertEqual(report['signed_rounds'],3)
        self.assertFalse(report['old_registry_plus_old_external_pins_excluded'])

    def test_missing_genesis_round_refused(self):
        self.stage(1)
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=self.rounds[1:])

    def test_missing_intermediate_round_refused(self):
        self.stage(2)
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=[self.rounds[0],self.rounds[2]])

    def test_duplicate_round_refused(self):
        self.stage(1)
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=[self.rounds[0],self.rounds[0]])

    def test_swapped_round_order_refused(self):
        self.stage(1)
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=list(reversed(self.rounds)))

    def test_stale_external_escrow_tip_refused(self):
        self.stage(1)
        with self.assertRaises(history.HistoryConflict):
            self.check(latest=escrow.bundle_digest(self.rounds[0]))

    def test_stale_registry_count_or_head_refused(self):
        self.stage(1)
        with self.assertRaises(registry.RegistryConflict):
            self.check(count=0)
        with self.assertRaises(registry.RegistryConflict):
            self.check(head=registry.GENESIS)

    def test_wrong_external_history_file_pin_refused(self):
        self.stage(0)
        with self.assertRaises(history.HistoryConflict):
            self.check(pin='f'*64)

    def test_duplicate_json_key_and_noncanonical_format_refused(self):
        self.stage(0)
        uncanonical=json.dumps(json.loads(self.history_raw)).encode()
        with self.assertRaises(history.HistoryConflict):
            self.check(raw=uncanonical,
                       pin=hashlib.sha256(uncanonical).hexdigest())
        duplicate=b'{"schema":"a","schema":"b","rounds":[]}\n'
        with self.assertRaises(history.HistoryConflict):
            self.check(raw=duplicate,
                       pin=hashlib.sha256(duplicate).hexdigest())

    def test_invalid_hex_and_missing_operator_refused(self):
        self.stage(0)
        obj=json.loads(self.history_raw)
        del obj['rounds'][0]['escrow-b']
        tampered=history._canonical(obj)
        with self.assertRaises(history.HistoryConflict):
            self.check(raw=tampered,pin=hashlib.sha256(tampered).hexdigest())
        obj=json.loads(self.history_raw)
        obj['rounds'][0]['escrow-a']='not-hex'
        tampered=history._canonical(obj)
        with self.assertRaises(history.HistoryConflict):
            self.check(raw=tampered,pin=hashlib.sha256(tampered).hexdigest())

    def test_distinct_signer_keys_required(self):
        self.stage(0)
        same=dict(self.pins)
        same['escrow-b']=same['escrow-a']
        with self.assertRaises(history.HistoryConflict):
            self.check(pins=same)

    def test_one_signer_substitutes_another_round_receipt(self):
        self.stage(1)
        rounds=[dict(x) for x in self.rounds]
        rounds[1]['escrow-b']=rounds[0]['escrow-b']
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=rounds)

    def test_valid_but_conflicting_signed_round_cannot_rewrite_registry(self):
        self.stage(1)
        rounds=[dict(x) for x in self.rounds]
        body = escrow.make_body(
            'escrow-c',1,'f'*64,self.current_checkpoint,
            escrow.bundle_digest(rounds[0]),'c'*32,fixture.TAG)
        output = self.path('conflicting-signed-history-')
        _sign(body,escrow.SCHEMA,escrow.DOMAIN,self.admins[2][1],output)
        rounds[1]['escrow-c']=output.read_bytes()
        with self.assertRaises(history.HistoryConflict):
            self.check(rounds=rounds)

    def test_comparison_of_two_independently_pinned_identical_histories(self):
        self.stage(1)
        result=self.check(comparison=self.history_raw,
                          comparison_pin=self.history_pin)
        self.assertTrue(result['two_submitted_archives_consistent'])
        self.assertFalse(result['all_conflicting_archives_discovered'])

    def test_conflicting_second_archive_even_with_valid_file_pin_refused(self):
        self.stage(1)
        rounds=[dict(x) for x in self.rounds]
        body=escrow.make_body(
            'escrow-a',1,self.current_head,self.current_checkpoint,
            escrow.bundle_digest(rounds[0]),'e'*32,fixture.TAG)
        output=self.path('equivocating-operator-')
        _sign(body,escrow.SCHEMA,escrow.DOMAIN,self.admins[0][1],output)
        rounds[1]['escrow-a']=output.read_bytes()
        alt=history.pack(rounds)
        with self.assertRaises(history.HistoryConflict):
            self.check(comparison=alt,
                       comparison_pin=hashlib.sha256(alt).hexdigest())

    def test_comparison_requires_separately_pinned_archive(self):
        self.stage(0)
        with self.assertRaises(history.HistoryConflict):
            self.check(comparison=self.history_raw)

    def test_replaying_old_registry_with_old_receipts_still_possible(self):
        self.stage(1)
        # Host restoring the registry to genesis, while an attacker also
        # substitutes signed genesis receipt and old external pin: this
        # remains possible and must never be called rollback prevention.
        with __import__('sqlite3').connect(self.registry) as con:
            con.execute('DELETE FROM accepted_replay_checkpoints')
        genesis=self.rounds[0]
        output=self.check(rounds=[genesis],count=0,head=registry.GENESIS,
                          checkpoint_pin=checkpoint.ANCHOR_GENESIS,
                          latest=escrow.bundle_digest(genesis))
        self.assertFalse(output['old_registry_plus_old_external_pins_excluded'])

    def test_cli_success_is_redacted_and_does_not_unlock(self):
        self.stage(0)
        private=self.path('escrow-history-private-')
        private.write_bytes(self.history_raw)
        private.chmod(0o600)
        args=[str(self.registry),str(private),self.history_pin,
              '--checkpoint-tag',fixture.TAG,'--expected-count','0',
              '--expected-head',registry.GENESIS,
              '--expected-checkpoint',checkpoint.ANCHOR_GENESIS,
              '--latest-escrow-sha256',self.latest]
        for role in escrow.ROLES:
            args.extend(('--'+role+'-public',str(self.keys[role]),
                         '--'+role+'-public-sha256',self.pins[role]))
        with contextlib.redirect_stdout(output := io.StringIO()):
            code = history.main(args)
        self.assertEqual(code,0,output.getvalue())
        summary=json.loads(output.getvalue())
        self.assertFalse(summary['witness_fence_retired'])
        self.assertNotIn('signature_hex',output.getvalue())
        self.assertNotIn('escrow_round_nonce',output.getvalue())


if __name__ == '__main__':
    unittest.main()
