"""Synthetic Stage 263H alternate runtime and generic argv custody inventory."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_record_linux_interpreted_writers as py_fixture
from tools import audit_record_linux_writer_inventory as binary
from tools import audit_record_linux_interpreted_writers as interpreted
from tools import audit_record_linux_launcher_inventory as alternate


class AlternativeLauncherTests(unittest.TestCase):
    setUp = py_fixture.InterpretedWriterTests.setUp
    make_manifest = py_fixture.InterpretedWriterTests.make_manifest
    process = py_fixture.InterpretedWriterTests.process
    python_proc = py_fixture.InterpretedWriterTests.python_proc
    enrolled = py_fixture.InterpretedWriterTests.enrolled

    def prepare(self):
        self.enrolled()
        self.shell = self.bin_dir/'bash'
        self.node = self.bin_dir/'node'
        self.shell.write_bytes(b'fake old shell')
        self.node.write_bytes(b'fake node')
        self.old_shell_script = self.root/'old'/'legacy.sh'
        self.old_shell_script.parent.mkdir()
        self.old_shell_script.write_bytes(b'echo fake')
        launchers = sorted((self.shell, self.node), key=str)
        self.launcher_raw = alternate._canonical({
            'schema': alternate.SCHEMA,
            'launchers': [
                {'path':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in launchers
            ],
            'modules':['tools.audit_record_custodian_tls'],
            'scripts':[str(self.old_shell_script)],
        })

    def inspect(self, raw=None, pin=None):
        evidence = self.launcher_raw if raw is None else raw
        return alternate.inspect(
            self.manifest, hashlib.sha256(self.manifest).hexdigest(),
            self.entry, hashlib.sha256(self.entry).hexdigest(),
            evidence, hashlib.sha256(evidence).hexdigest()
            if pin is None else pin,
            self.db, self.device, self.inode, proc_root=self.proc)

    def userspace(self, exe, argv, *, pid=123):
        node = self.process(pid=pid, exe=exe)
        (node/'cmdline').write_bytes(
            b'\x00'.join(x.encode('utf-8') for x in argv)+b'\x00')
        return node

    def test_empty_scan_reports_advisory_only(self):
        self.prepare()
        result = self.inspect()
        self.assertTrue(result['alternative_launcher_procfs_scanned_twice'])
        self.assertTrue(result['native_and_python_inventory_passed'])
        self.assertFalse(result['all_alternative_runtimes_excluded'])
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['future_writer_launch_prevented'])

    def test_shell_is_refused_even_without_known_script(self):
        self.prepare()
        self.userspace(self.shell, [str(self.shell), '-c', 'echo benign'])
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_deleted_launcher_executable_detected(self):
        self.prepare()
        self.userspace(str(self.node)+' (deleted)', ['node', '-e', '3'])
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_unknown_interpreter_with_known_shell_script(self):
        self.prepare()
        self.userspace(self.other, ['some-other-runtime',
                                   str(self.old_shell_script)])
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_unknown_interpreter_python_module_detected(self):
        self.prepare()
        self.userspace(self.other, ['python-fork', '-m',
                                   'tools.audit_record_custodian_tls'])
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_env_wrapper_with_nested_module_detected(self):
        self.prepare()
        self.userspace(self.other, ['/usr/bin/env', '-S', 'python3',
                                   '-m', 'tools.audit_record_custodian_tls'])
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_unenrolled_runtime_and_argv_not_claimed_complete(self):
        self.prepare()
        self.userspace(self.other, ['unknown', '-e', 'unknown.js'])
        result = self.inspect()
        self.assertFalse(result['all_alternative_runtimes_excluded'])
        self.assertFalse(result['argv_is_authenticated_provenance'])

    def test_argv_substring_does_not_match_exact_module(self):
        self.prepare()
        self.userspace(self.other, ['unknown', '-m',
                                   'prefix.tools.audit_record_custodian_tls'])
        result = self.inspect()
        self.assertFalse(result['future_writer_launch_prevented'])

    def test_broken_userspace_cmdline_refused(self):
        self.prepare()
        p=self.userspace(self.other, ['unknown'])
        (p/'cmdline').unlink()
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_bad_utf8_and_unterminated_cmdline_refused(self):
        self.prepare()
        p=self.userspace(self.other, ['unknown'])
        for raw in (b'bad-command', b'\xff\x00'):
            (p/'cmdline').write_bytes(raw)
            with self.assertRaises(binary.InventoryConflict):
                self.inspect()

    def test_kernel_thread_without_exe_can_be_empty(self):
        self.prepare()
        p=self.process(pid=333)
        (p/'cmdline').write_bytes(b'')
        result=self.inspect()
        self.assertFalse(result['witness_fence_retired'])

    def test_userspace_cmdline_without_executable_refused(self):
        self.prepare()
        p=self.process(pid=333)
        (p/'cmdline').write_bytes(b'python3\x00-m\x00foo\x00')
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_missing_kernel_thread_cmdline_refused(self):
        self.prepare()
        self.process(pid=333)
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()

    def test_manifest_signature_pin_tamper_refused(self):
        self.prepare()
        with self.assertRaises(binary.InventoryConflict):
            self.inspect(pin='f'*64)

    def test_duplicate_launcher_paths_and_invalid_scripts_refused(self):
        self.prepare()
        base=json.loads(self.launcher_raw)
        base['launchers'].append(base['launchers'][-1])
        with self.assertRaises(ValueError):
            self.inspect(raw=alternate._canonical(base))
        base=json.loads(self.launcher_raw)
        base['scripts']=['../unsafe.sh']
        with self.assertRaises(ValueError):
            self.inspect(raw=alternate._canonical(base))

    def test_unsorted_and_duplicate_module_catalogue_refused(self):
        self.prepare()
        for modules in (
            ['tools.z','tools.a'], ['tools.z','tools.z']):
            with self.subTest(modules=modules):
                obj=json.loads(self.launcher_raw)
                obj['modules']=modules
                with self.assertRaises(ValueError):
                    self.inspect(raw=alternate._canonical(obj))

    def test_new_launcher_appearing_only_on_second_scan_refused(self):
        self.prepare()
        original=alternate._scan
        calls=[0]
        def race(*args):
            calls[0]+=1
            if calls[0]==2:
                self.userspace(self.shell, ['bash', '-c', 'echo hello'],pid=555)
            return original(*args)
        with patch.object(alternate,'_scan',side_effect=race):
            with self.assertRaises(binary.InventoryConflict):
                self.inspect()

    def test_changed_pid_starttime_refused(self):
        self.prepare()
        self.userspace(self.other, ['unknown'])
        original=alternate._process_identity
        count=[0]
        def changed(fd,pid):
            count[0]+=1
            return original(fd,pid)+(1 if count[0]==2 else 0)
        with patch.object(alternate,'_process_identity',side_effect=changed):
            with self.assertRaises(binary.InventoryConflict):
                self.inspect()

    def test_combined_open_sqlite_fd_guard_cannot_be_skipped(self):
        self.prepare()
        self.process(pid=999,exe=self.other,fds={5:self.db})
        with self.assertRaises(binary.InventoryConflict):
            self.inspect()


if __name__ == '__main__':
    unittest.main()
