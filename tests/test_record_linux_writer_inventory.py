"""Synthetic stage-263F /proc writer catalogue and open-descriptor inventory."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_record_linux_writer_inventory as audit


class WriterProcessInventoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.proc = self.root/'proc'
        self.proc.mkdir()
        self.priv = self.root/'custody'
        self.priv.mkdir()
        self.db = self.priv/'anchors.sqlite'
        self.db.write_bytes(b'synthetic-sqlite-placeholder')
        self.bin_dir = self.root/'binaries'
        self.bin_dir.mkdir()
        self.writer = self.bin_dir/'old-custodian'
        self.writer.write_bytes(b'writer version old')
        self.other = self.bin_dir/'unrelated'
        self.other.write_bytes(b'unrelated executable')
        self.manifest = self.make_manifest()
        st = self.db.stat()
        self.device, self.inode = st.st_dev, st.st_ino

    def make_manifest(self, paths=None):
        paths = [self.writer] if paths is None else paths
        return audit._canonical({
            'schema': audit.SCHEMA,
            'executables': [
                {'path': str(path), 'sha256': hashlib.sha256(
                    path.read_bytes()).hexdigest()}
                for path in sorted(paths)
            ],
        })

    def process(self, pid=123, exe=None, fds=None, *, start=12345, raw_stat=None):
        directory = self.proc/str(pid)
        directory.mkdir()
        fd = directory/'fd'
        fd.mkdir()
        if exe is not None:
            (directory/'exe').symlink_to(exe)
        if raw_stat is None:
            fields = ['S'] + ['0']*18 + [str(start)] + ['0']*2
            raw_stat = f"{pid} (test worker) "+' '.join(fields)+'\n'
        (directory/'stat').write_text(raw_stat)
        for name, target in (fds or {}).items():
            (fd/str(name)).symlink_to(target)
        return directory

    def run_inventory(self, *, manifest=None, pin=None):
        raw = self.manifest if manifest is None else manifest
        return audit.inventory(raw, hashlib.sha256(raw).hexdigest()
                               if pin is None else pin,
                               self.db, self.device, self.inode,
                               proc_root=self.proc)

    def test_empty_process_tree_is_advisory_not_authorization(self):
        result = self.run_inventory()
        self.assertTrue(result['bounded_procfs_scan_completed_twice'])
        self.assertFalse(result['witness_fence_retirement_authorized'])
        self.assertFalse(result['continuous_writer_revocation_proved'])
        self.assertFalse(result['all_possible_writer_processes_excluded'])

    def test_known_live_writer_without_database_fd_rejected(self):
        self.process(exe=self.writer)
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_deleted_old_executable_path_remains_detectable(self):
        self.process(exe=str(self.writer)+' (deleted)')
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_unknown_binary_holding_custody_file_rejected(self):
        self.process(exe=self.other, fds={3:self.db})
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_parent_directory_fd_is_rejected(self):
        self.process(exe=self.other, fds={4:self.priv})
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_sidecar_journal_fd_is_rejected(self):
        journal = Path(str(self.db)+'-journal')
        journal.write_bytes(b'synthetic-sidecar')
        self.process(exe=self.other, fds={5:journal})
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_unrelated_binary_and_unrelated_fd_pass_advisory_only(self):
        self.process(exe=self.other, fds={7:self.other})
        result = self.run_inventory()
        self.assertTrue(result['bounded_procfs_scan_completed_twice'])
        self.assertFalse(result['witness_fence_retired'])

    def test_missing_process_stat_and_fd_refused(self):
        proc = self.process(exe=self.other)
        (proc/'stat').unlink()
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()
        (proc/'stat').write_text('123 (bad) S 0\n')
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_broken_fd_link_refused_not_skipped(self):
        self.process(exe=self.other, fds={3:self.root/'missing-file'})
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_symlinked_pid_directory_cannot_escape_scan(self):
        outside = self.root/'out-of-proc'
        outside.mkdir()
        (self.proc/'789').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_pid_reuse_during_scan_refused(self):
        self.process(exe=self.other)
        original = audit._process_identity
        calls = [0]
        def racing(fd, pid):
            calls[0] += 1
            return original(fd, pid) + (1 if calls[0] == 2 else 0)
        with patch.object(audit, '_process_identity', side_effect=racing):
            with self.assertRaises(audit.InventoryConflict):
                self.run_inventory()

    def test_second_scan_new_writer_is_refused(self):
        self.process(exe=self.other)
        original = audit._scan
        calls = [0]
        def changed(*args):
            calls[0] += 1
            if calls[0] == 2:
                self.process(pid=456, exe=self.writer)
            return original(*args)
        with patch.object(audit, '_scan', side_effect=changed):
            with self.assertRaises(audit.InventoryConflict):
                self.run_inventory()

    def test_fd_count_bound_enforced(self):
        self.process(exe=self.other, fds={3:self.other, 4:self.other})
        with patch.object(audit, 'MAX_FDS', 1):
            with self.assertRaises(audit.InventoryConflict):
                self.run_inventory()

    def test_missing_manifest_pin_or_wrong_pin_rejected(self):
        for pin in ('f'*64, 'bad'):
            with self.subTest(pin=pin):
                with self.assertRaises((ValueError, audit.InventoryConflict)):
                    self.run_inventory(pin=pin)

    def test_duplicate_manifest_json_key_rejected(self):
        dup = ('{"schema":"'+audit.SCHEMA+
               '","schema":"'+audit.SCHEMA+'","executables":[]}\n').encode()
        with self.assertRaises(ValueError):
            self.run_inventory(manifest=dup)

    def test_duplicate_or_unsorted_known_paths_rejected(self):
        entry = json.loads(self.manifest)['executables'][0]
        dup = audit._canonical({
            'schema': audit.SCHEMA,
            'executables': [entry, entry],
        })
        with self.assertRaises(ValueError):
            self.run_inventory(manifest=dup)

    def test_symlinked_enrolled_custody_file_refused(self):
        actual = self.priv/'original.sqlite'
        self.db.rename(actual)
        self.db.symlink_to(actual)
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_symlinked_enrolled_custody_directory_refused(self):
        actual = self.root/'original-custody'
        self.priv.rename(actual)
        self.priv.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_symlinked_sqlite_sidecar_refused(self):
        (Path(str(self.db)+'-wal')).symlink_to(self.other)
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_enrolled_database_inode_mismatch_refused(self):
        self.inode += 1
        with self.assertRaises(audit.InventoryConflict):
            self.run_inventory()

    def test_invalid_manifest_path_rejected(self):
        for path in ('relative/writer', '/bin/../writer', '/bad//writer'):
            with self.subTest(path=path):
                body = {'schema': audit.SCHEMA,
                        'executables': [{'path':path, 'sha256':'a'*64}]}
                with self.assertRaises(ValueError):
                    self.run_inventory(manifest=audit._canonical(body))


if __name__ == '__main__':
    unittest.main()
