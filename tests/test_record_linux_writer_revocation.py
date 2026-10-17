"""Synthetic stage-263E masked-service and writer-UID revocation observations."""
import os
import stat
import unittest

from tests import test_record_witness_linux_quiescence as linux_fixture
from tools.audit_record_anchor_handoff import _canonical
from tools.audit_record_witness_linux_quiescence import QuiescenceConflict
from tools.audit_record_linux_writer_revocation import (
    PROPERTIES, RevocationConflict, _custody_file, _parse_unit, _unit, assess,
)

SCOPE = linux_fixture.SCOPE
BOOT = linux_fixture.BOOT
UNIT = 'custody-writer.service'


class WriterRevocationTests(unittest.TestCase):
    setUp = linux_fixture.LinuxCgroupObservationTests.setUp
    request = linux_fixture.LinuxCgroupObservationTests.request
    path = linux_fixture.LinuxCgroupObservationTests.path
    stop = linux_fixture.LinuxCgroupObservationTests.stop
    new_offer = linux_fixture.LinuxCgroupObservationTests.new_offer
    make_offer_and_deposit = (
        linux_fixture.LinuxCgroupObservationTests.make_offer_and_deposit)
    make_cgroup = linux_fixture.LinuxCgroupObservationTests.make_cgroup
    write_controls = linux_fixture.LinuxCgroupObservationTests.write_controls
    snapshot = linux_fixture.LinuxCgroupObservationTests.snapshot
    signed_stop_for = linux_fixture.LinuxCgroupObservationTests.signed_stop_for

    @classmethod
    def setUpClass(cls):
        linux_fixture.LinuxCgroupObservationTests.setUpClass()
        for name in ('ca', 'server_key', 'server_cert', 'server_pin',
                     'client_key', 'client_cert', 'client_pin',
                     'sign_key', 'sign_pub', 'sign_pub_pin'):
            setattr(cls, name,
                    getattr(linux_fixture.LinuxCgroupObservationTests, name))

    @classmethod
    def tearDownClass(cls):
        linux_fixture.LinuxCgroupObservationTests.tearDownClass()

    def prepare(self):
        self.make_cgroup()
        self.original = self.request()
        self.observation = self.snapshot(self.original)
        self.signed, self.supervisor_public, self.supervisor_pin = (
            self.signed_stop_for(self.original, self.observation))
        db = self.custody.stat()
        self.service_uid = os.getuid()+1
        self.db_device, self.db_inode = db.st_dev, db.st_ino
        self.calls = 0

    def unit_properties(self, **changes):
        body = {
            'Id': UNIT, 'LoadState': 'masked',
            'UnitFileState': 'masked', 'ActiveState': 'inactive',
            'SubState': 'dead', 'CanStart': 'no', 'NeedDaemonReload': 'no',
            'MainPID': '0', 'ControlPID': '0', 'Job': '0',
            'FragmentPath': '/dev/null',
        }
        body.update(changes)
        return (''.join(k+'='+body[k]+'\n' for k in PROPERTIES)).encode()

    def reader(self, unit):
        self.calls += 1
        return self.unit_properties()

    def check(self, *, reader=None):
        return assess(
            self.original, self.signed, _canonical(self.observation),
            self.supervisor_public, self.supervisor_pin,
            supervisor_tag='independent-supervisor',
            cgroup_scope=SCOPE, pinned_boot_id=BOOT,
            cgroup_device=self.pin[0], cgroup_inode=self.pin[1],
            service_unit=UNIT, service_uid=self.service_uid,
            custody_database=self.custody,
            db_device=self.db_device, db_inode=self.db_inode,
            systemd_reader=self.reader if reader is None else reader,
            cgroup_root=self.root, boot_id_path=self.boot_path)

    def test_masked_empty_cgroup_and_disjoint_uid_is_advisory_only(self):
        self.prepare()
        report = self.check()
        self.assertEqual(self.calls, 2)
        self.assertTrue(report['systemd_unit_masked_and_inactive_at_observation'])
        self.assertTrue(report['enrolled_service_uid_denied_by_basic_file_modes'])
        self.assertFalse(report['durable_global_writer_revocation_proved'])
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertFalse(report['witness_fence_retired'])

    def test_not_masked_or_runtime_only_mask_refused(self):
        self.prepare()
        for field, value in (
            ('UnitFileState', 'enabled'), ('UnitFileState', 'masked-runtime'),
            ('LoadState', 'loaded'), ('FragmentPath', '/etc/systemd/foo'),
            ('CanStart', 'yes'), ('NeedDaemonReload', 'yes')):
            with self.subTest(field=field, value=value):
                with self.assertRaises(RevocationConflict):
                    self.check(reader=lambda unit: self.unit_properties(
                        **{field:value}))

    def test_active_service_or_remaining_process_refused(self):
        self.prepare()
        for change in ({'ActiveState':'active'}, {'SubState':'running'},
                       {'MainPID':'123'}, {'ControlPID':'123'},
                       {'Job':'123'}):
            with self.subTest(change=change):
                with self.assertRaises(RevocationConflict):
                    self.check(reader=lambda unit: self.unit_properties(**change))

    def test_systemd_status_changes_between_reads_refused(self):
        self.prepare()
        def fluctuating(unit):
            self.calls += 1
            return self.unit_properties() if self.calls == 1 else (
                self.unit_properties(NeedDaemonReload='yes'))
        with self.assertRaises(RevocationConflict):
            self.check(reader=fluctuating)

    def test_service_uid_equal_to_file_owner_refused(self):
        self.prepare()
        self.service_uid = os.getuid()
        with self.assertRaises((RevocationConflict, ValueError)):
            self.check()

    def test_service_uid_equal_to_parent_owner_refused(self):
        self.prepare()
        self.service_uid = self.custody.parent.stat().st_uid
        with self.assertRaises((RevocationConflict, ValueError)):
            self.check()

    def test_group_or_other_file_access_refused(self):
        self.prepare()
        self.custody.chmod(0o660)
        with self.assertRaises(RevocationConflict):
            self.check()

    def test_world_traversable_parent_refused(self):
        self.prepare()
        self.custody.parent.chmod(0o755)
        with self.assertRaises(RevocationConflict):
            self.check()

    def test_replaced_custody_inode_refused(self):
        self.prepare()
        self.db_inode += 1
        with self.assertRaises(RevocationConflict):
            self.check()
 
    def test_symlinked_custody_database_refused(self):
        self.prepare()
        real = self.custody.with_name('saved-custody.sqlite')
        self.custody.rename(real)
        self.custody.symlink_to(real)
        with self.assertRaises(OSError):
            self.check()

    def test_cgroup_changes_or_stop_signature_changed_refused(self):
        self.prepare()
        self.write_controls(self.scope_path, procs='9999\n')
        with self.assertRaises(QuiescenceConflict):
            self.check()

    def test_systemd_unit_injection_and_duplicate_fields_refused(self):
        for bad in ('../evil.service', 'evil;rm.service',
                    '/tmp/evil.service', 'foo.socket', 'a'*128+'.service'):
            with self.subTest(unit=bad):
                with self.assertRaises(ValueError):
                    _unit(bad)
        raw = self.unit_properties(Id='wrong.service')
        with self.assertRaises(RevocationConflict):
            _parse_unit(raw, UNIT)
        with self.assertRaises(RevocationConflict):
            _parse_unit(self.unit_properties()+b'Id='+UNIT.encode()+b'\n', UNIT)

    def test_unreadable_or_invalid_service_uid_refused(self):
        self.prepare()
        for uid in (0, -1, '1001'):
            with self.subTest(uid=uid):
                with self.assertRaises(ValueError):
                    _custody_file(self.custody, service_uid=uid,
                                  db_device=self.db_device,
                                  db_inode=self.db_inode)


if __name__ == '__main__':
    unittest.main()
