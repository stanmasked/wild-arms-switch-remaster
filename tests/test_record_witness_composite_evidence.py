"""Stage 263J: synthetic cross-report, signed session and composite pin tests."""
import copy
import hashlib
import json
import unittest

from tests import test_record_witness_linux_quiescence as fixture
from tools.audit_record_anchor_handoff import _canonical
from tools import audit_record_witness_composite_evidence as composite


class CompositeEvidenceTests(unittest.TestCase):
    setUp = fixture.LinuxCgroupObservationTests.setUp
    request = fixture.LinuxCgroupObservationTests.request
    path = fixture.LinuxCgroupObservationTests.path
    stop = fixture.LinuxCgroupObservationTests.stop
    make_cgroup = fixture.LinuxCgroupObservationTests.make_cgroup
    snapshot = fixture.LinuxCgroupObservationTests.snapshot
    signed_stop_for = fixture.LinuxCgroupObservationTests.signed_stop_for
    new_offer = fixture.LinuxCgroupObservationTests.new_offer
    make_offer_and_deposit = (
        fixture.LinuxCgroupObservationTests.make_offer_and_deposit)

    @classmethod
    def setUpClass(cls):
        fixture.LinuxCgroupObservationTests.setUpClass()
        for name in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, name,
                    getattr(fixture.LinuxCgroupObservationTests, name))

    @classmethod
    def tearDownClass(cls):
        fixture.LinuxCgroupObservationTests.tearDownClass()

    def init_capture(self):
        self.make_cgroup()
        self.original = self.request()
        self.cgroup = _canonical(self.snapshot(self.original))
        self.stop_raw, self.public, self.pin = self.signed_stop_for(
            self.original, json.loads(self.cgroup))
        self.reports = {}
        for name, (schema, positives, negatives, hashes) in (
                composite.SPECS.items()):
            row = {'schema': schema}
            row.update({field: True for field in positives})
            row.update({field: False for field in negatives})
            for field in hashes:
                row[field] = (
                    'reservation-not-observed-in-snapshot'
                    if field == 'negative_snapshot_classification' else 'a'*64)
            self.reports[name] = _canonical(row)

    def build(self, reports=None, *, original=None, stop=None,
              cgroup=None, pin=None):
        return composite.build(
            self.original if original is None else original,
            self.stop_raw if stop is None else stop,
            self.cgroup if cgroup is None else cgroup,
            self.reports if reports is None else reports,
            self.public, self.pin if pin is None else pin,
            supervisor_tag='independent-supervisor')

    def verify(self, manifest, *, reports=None, stop=None,
               cgroup=None, original=None, expected_pin=None):
        raw = _canonical(manifest)
        return composite.verify(
            raw, hashlib.sha256(raw).hexdigest()
            if expected_pin is None else expected_pin,
            self.original if original is None else original,
            self.stop_raw if stop is None else stop,
            self.cgroup if cgroup is None else cgroup,
            self.reports if reports is None else reports,
            self.public, self.pin,
            supervisor_tag='independent-supervisor')

    def rewritten(self, name, **changes):
        reports = dict(self.reports)
        row = json.loads(reports[name])
        row.update(changes)
        reports[name] = _canonical(row)
        return reports

    def test_signed_exact_request_and_eight_reports_bound(self):
        self.init_capture()
        manifest = self.build()
        self.assertEqual(set(manifest['report_bindings']),
                         set(composite.SPECS))
        self.assertEqual(manifest['session']['stop_session_nonce'], '6'*32)
        result = self.verify(manifest)
        self.assertTrue(result['all_eight_report_bytes_bound'])
        self.assertFalse(result['report_authenticity_independently_proved'])
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['witness_fence_retired'])

    def test_identical_bytes_produce_identical_manifest_digest(self):
        self.init_capture()
        self.assertEqual(_canonical(self.build()), _canonical(self.build()))

    def test_missing_or_extra_report_refused(self):
        self.init_capture()
        for reports in ({k:v for k,v in self.reports.items()
                         if k != 'activation'}, {**self.reports, 'extra': b'{}'}):
            with self.assertRaises(composite.CompositeConflict):
                self.build(reports)

    def test_signed_stop_or_original_request_swapped(self):
        self.init_capture()
        swapped = self.request(nonce='e'*32)
        with self.assertRaises(ValueError):
            self.build(original=swapped)
        other_stop, _, _ = self.signed_stop_for(
            swapped, json.loads(self.cgroup))
        with self.assertRaises(ValueError):
            self.build(stop=other_stop)

    def test_changed_cgroup_content_breaks_signed_binding(self):
        self.init_capture()
        value = json.loads(self.cgroup)
        value['scope'] = 'different.slice/else.service'
        with self.assertRaises(composite.CompositeConflict):
            self.build(cgroup=_canonical(value))

    def test_changed_cgroup_nonce_refused(self):
        self.init_capture()
        value = json.loads(self.cgroup)
        value['stop_session_nonce'] = 'd'*32
        with self.assertRaises(composite.CompositeConflict):
            self.build(cgroup=_canonical(value))

    def test_missing_cgroup_nodes_refused(self):
        self.init_capture()
        value = json.loads(self.cgroup)
        value['nodes'] = []
        with self.assertRaises(composite.CompositeConflict):
            self.build(cgroup=_canonical(value))

    def test_mixed_negative_result_classifications_refused(self):
        self.init_capture()
        reports = self.rewritten(
            'quarantine', negative_snapshot_classification=
            'checkpoint-not-committed-in-snapshot')
        with self.assertRaises(composite.CompositeConflict):
            self.build(reports)

    def test_invalid_classification_refused(self):
        self.init_capture()
        with self.assertRaises(composite.CompositeConflict):
            self.build(self.rewritten(
                'preflight', negative_snapshot_classification='success'))

    def test_missing_or_extra_report_fields_refused(self):
        self.init_capture()
        altered = self.rewritten('activation', unknown_field=True)
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)
        data = json.loads(self.reports['activation'])
        del data['future_activation_prevented']
        altered = dict(self.reports, activation=_canonical(data))
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)

    def test_fake_global_revocation_claim_refused(self):
        self.init_capture()
        altered = self.rewritten('revocation',
                                 durable_global_writer_revocation_proved=True)
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)

    def test_unpassed_scan_cannot_enter_successful_manifest(self):
        self.init_capture()
        altered = self.rewritten('launchers',
                                 alternative_launcher_procfs_scanned_twice=False)
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)

    def test_noncanonical_report_and_duplicate_json_key_refused(self):
        self.init_capture()
        altered = dict(self.reports)
        altered['cgroup'] = json.dumps(
            json.loads(altered['cgroup'])).encode()
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)
        altered['cgroup'] = (
            b'{"schema":"x","schema":"y"}\n')
        with self.assertRaises(composite.CompositeConflict):
            self.build(altered)

    def test_malformed_observation_digest_refused(self):
        self.init_capture()
        with self.assertRaises(composite.CompositeConflict):
            self.build(self.rewritten('binary', observation_sha256='invalid'))

    def test_report_byte_swap_rejected_by_external_manifest_pin(self):
        self.init_capture()
        manifest = self.build()
        changed = self.rewritten('binary', observation_sha256='f'*64)
        with self.assertRaises(composite.CompositeConflict):
            self.verify(manifest, reports=changed)

    def test_reusing_old_signed_stop_with_new_request_refused(self):
        self.init_capture()
        previous = self.build()
        other = self.request(nonce='a'*32)
        with self.assertRaises(ValueError):
            self.verify(previous, original=other)

    def test_wrong_external_manifest_pin_refused(self):
        self.init_capture()
        with self.assertRaises(composite.CompositeConflict):
            self.verify(self.build(), expected_pin='f'*64)

    def test_modified_manifest_digest_even_with_new_file_pin_refused(self):
        self.init_capture()
        copy_of_bundle = copy.deepcopy(self.build())
        copy_of_bundle['manifest_sha256'] = 'f'*64
        with self.assertRaises(composite.CompositeConflict):
            self.verify(copy_of_bundle)

    def test_mutated_report_binding_without_payload_change_refused(self):
        self.init_capture()
        copy_of_bundle = copy.deepcopy(self.build())
        copy_of_bundle['report_bindings']['activation']['report_sha256'] = 'f'*64
        with self.assertRaises(composite.CompositeConflict):
            self.verify(copy_of_bundle)

    def test_raw_bundle_requires_exact_canonical_file(self):
        self.init_capture()
        bundle = self.build()
        raw = json.dumps(bundle).encode()
        with self.assertRaises(composite.CompositeConflict):
            composite.verify(
                raw, hashlib.sha256(raw).hexdigest(),
                self.original, self.stop_raw, self.cgroup,
                self.reports, self.public, self.pin,
                supervisor_tag='independent-supervisor')

    def test_public_key_pin_mismatch_refused(self):
        self.init_capture()
        with self.assertRaises(ValueError):
            self.build(pin='f'*64)

    def test_report_type_confusion_refused(self):
        self.init_capture()
        reports = dict(self.reports)
        reports['binary'], reports['activation'] = (
            reports['activation'], reports['binary'])
        with self.assertRaises(composite.CompositeConflict):
            self.build(reports)


if __name__ == '__main__':
    unittest.main()
