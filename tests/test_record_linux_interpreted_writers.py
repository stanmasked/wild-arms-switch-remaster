"""Stage 263G: synthetic interpreted writer (python -m/script/-c) regressions."""
import hashlib
import json
import unittest
from unittest.mock import patch

from tests import test_record_linux_writer_inventory as base_fixture
from tools import audit_record_linux_interpreted_writers as app
from tools import audit_record_linux_writer_inventory as base


class InterpretedWriterTests(unittest.TestCase):
    setUp = base_fixture.WriterProcessInventoryTests.setUp
    process = base_fixture.WriterProcessInventoryTests.process
    make_manifest = base_fixture.WriterProcessInventoryTests.make_manifest

    def enrolled(self):
        self.python = self.bin_dir/'python3.11'
        self.python.write_bytes(b'synthetic Python interpreter executable')
        self.script = self.root/'custodian'/'old-custodian.py'
        self.script.parent.mkdir()
        self.script.write_bytes(b'# synthetic script')
        self.entry = app._canonical({
            'schema': app.SCHEMA,
            'interpreters': [{
                'path': str(self.python),
                'sha256': hashlib.sha256(self.python.read_bytes()).hexdigest(),
            }],
            'modules': ['tools.audit_record_custodian_recovery',
                        'tools.audit_record_custodian_tls'],
            'scripts': [str(self.script)],
        })

    def check(self, *, entry=None, pin=None):
        raw = self.entry if entry is None else entry
        return app.inspect(
            self.manifest, hashlib.sha256(self.manifest).hexdigest(),
            raw, hashlib.sha256(raw).hexdigest() if pin is None else pin,
            self.db, self.device, self.inode, proc_root=self.proc)

    def python_proc(self, argv, *, pid=123, exe=None):
        path = self.process(pid=pid, exe=self.python if exe is None else exe)
        (path/'cmdline').write_bytes(
            b'\x00'.join(s.encode('utf-8') for s in argv)+b'\x00')
        return path

    def test_empty_host_has_no_recovery_authorization(self):
        self.enrolled()
        report=self.check()
        self.assertTrue(report['known_binary_and_fd_inventory_passed'])
        self.assertFalse(report['enrolled_python_interpreters_observed_live'])
        self.assertFalse(report['witness_fence_retirement_authorized'])
        self.assertFalse(report['future_writer_restart_excluded'])

    def test_registered_python_m_module_fails_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), '-m',
                          'tools.audit_record_custodian_tls'])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_registered_python_script_fails_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), str(self.script)])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_old_interpreter_with_removed_executable_fails_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), '-m',
                          'tools.audit_record_custodian_tls'],
                         exe=str(self.python)+' (deleted)')
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_unknown_python_module_still_fails_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), '-I', '-m', 'unknown.module'])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_python_dash_c_dynamic_code_fails_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), '-c', 'import sqlite3'])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_python_stdin_dashes_fail_closed(self):
        self.enrolled()
        self.python_proc([str(self.python), '-'])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_unknown_script_not_whitelisted_by_manifest(self):
        self.enrolled()
        self.python_proc([str(self.python), '/tmp/other.py'])
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_unenrolled_python_executable_not_claimed_as_global_revocation(self):
        self.enrolled()
        another = self.bin_dir/'python-elsewhere'
        another.write_bytes(b'other interpreter')
        self.python_proc([str(another), '-m',
                          'tools.audit_record_custodian_tls'], exe=another)
        report=self.check()
        self.assertFalse(report['unenrolled_python_versions_excluded'])
        self.assertFalse(report['unknown_script_and_module_writers_excluded'])

    def test_broken_or_missing_cmdline_refuses_observation(self):
        self.enrolled()
        proc=self.python_proc([str(self.python), '-m',
                               'tools.audit_record_custodian_tls'])
        (proc/'cmdline').unlink()
        with self.assertRaises(base.InventoryConflict):
            self.check()
        (proc/'cmdline').write_bytes(b'incomplete-cmdline')
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_oversized_or_invalid_utf8_cmdline_fails_closed(self):
        self.enrolled()
        proc=self.python_proc([str(self.python), '-c', 'x'])
        (proc/'cmdline').write_bytes(b'x'*(app.MAX_CMDLINE+1))
        with self.assertRaises(base.InventoryConflict):
            self.check()
        (proc/'cmdline').write_bytes(b'python\x00\xff\x00')
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_manifest_tamper_and_duplicate_or_unsorted_modules(self):
        self.enrolled()
        with self.assertRaises(base.InventoryConflict):
            self.check(pin='f'*64)
        item=json.loads(self.entry)
        item['modules']=['tools.z', 'tools.a']
        with self.assertRaises(ValueError):
            self.check(entry=app._canonical(item))
        item['modules']=['tools.z', 'tools.z']
        with self.assertRaises(ValueError):
            self.check(entry=app._canonical(item))

    def test_unsafe_script_path_and_untrusted_interpreter_digest(self):
        self.enrolled()
        obj=json.loads(self.entry)
        obj['scripts']=['../../test.py']
        with self.assertRaises(ValueError):
            self.check(entry=app._canonical(obj))
        obj=json.loads(self.entry)
        obj['interpreters'][0]['sha256']='not-a-digest'
        with self.assertRaises(ValueError):
            self.check(entry=app._canonical(obj))

    def test_enrolled_python_added_between_scans_is_detected(self):
        self.enrolled()
        original=app._interpreted_scan
        calls=[0]
        def race(*args):
            calls[0]+=1
            if calls[0]==2:
                self.python_proc([str(self.python), '-m',
                                  'tools.audit_record_custodian_tls'], pid=555)
            return original(*args)
        with patch.object(app, '_interpreted_scan', side_effect=race):
            with self.assertRaises(base.InventoryConflict):
                self.check()

    def test_enrolled_process_starttime_reuse_detected(self):
        self.enrolled()
        self.python_proc([str(self.python), '-m',
                          'tools.audit_record_custodian_tls'])
        # Base binary inventory checks PID identity first.
        original=base._process_identity
        counter=[0]
        def reused(fd,pid):
            counter[0]+=1
            return original(fd,pid)+(1 if counter[0]==2 else 0)
        with patch.object(base, '_process_identity', side_effect=reused):
            with self.assertRaises(base.InventoryConflict):
                self.check()

    def test_binary_and_database_descriptor_guard_not_bypassed(self):
        self.enrolled()
        self.process(pid=234, exe=self.other, fds={3:self.db})
        with self.assertRaises(base.InventoryConflict):
            self.check()

    def test_procfs_incomplete_symlink_pid_fails_closed(self):
        self.enrolled()
        outside=self.root/'outside'
        outside.mkdir()
        (self.proc/'999').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(base.InventoryConflict):
            self.check()


if __name__ == '__main__':
    unittest.main()
