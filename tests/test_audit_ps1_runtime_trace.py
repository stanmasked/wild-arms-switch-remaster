"""Synthetic-only capture correlation tests; no genuine game bytes or emulator logs."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_ps1_runtime_trace import audit_capture  # noqa: E402


def events():
    return [
        {'kind': 'watchpoint_write', 'tick': 100, 'address': '0x800D2EA0',
         'width': 4, 'pc': '0x80012340', 'after': '0x801E0000'},
        {'kind': 'transfer_call', 'tick': 200, 'pc': '0x80058B00',
         'target': '0x8002356C', 'a0': '0x801E0000',
         'a1': '0x80183000', 'a2': 4096},
        {'kind': 'disc_read', 'tick': 250, 'lba': 38503, 'sectors': 2},
        {'kind': 'ram_snapshot', 'tick': 300, 'pc': '0x80058B4C'},
    ]


class TraceCorrelationTests(unittest.TestCase):
    def analyze(self, events_override=None, mutate_ram=False, schema=1):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace_path = root / 'events.json'
            trace_path.write_text(json.dumps({'schema': schema, 'kind': 'PRIVATE_PS1_RUNTIME_EVENTS',
                                              'events': events() if events_override is None else events_override}),
                                  encoding='utf-8')
            container = root / 'CDFLR.BIN'
            payload = bytes(i % 251 for i in range(8192))
            container.write_bytes(payload)
            ram = bytearray(2 * 1024 * 1024)
            ram[0x183000:0x184000] = payload[:4096]
            if mutate_ram:
                ram[0x183222] ^= 0xFF
            dump = root / 'ps1-ram.bin'
            dump.write_bytes(ram)
            return audit_capture(trace_path, container, dump, count=4096)

    def test_positive_capture_correlates_but_causality_unproven(self):
        result = self.analyze()
        self.assertEqual(result['correlation_status'], 'TRACE_AND_BYTES_CORRELATED')
        self.assertTrue(result['source_slot_write_agrees_with_a0'])
        self.assertEqual(result['candidate_cdflr_range_read_count_before_snapshot'], 1)
        self.assertEqual(result['byte_comparison']['comparison_status'], 'EXACT_MATCH')
        self.assertTrue(result['interpretation']['named_resource_origin_not_proven_by_correlation_alone'])
        self.assertTrue(result['interpretation']['trace_is_user_supplied_not_independently_authenticated'])

    def test_no_watchpoint_cannot_claim_provenance(self):
        result = self.analyze(events()[1:])
        self.assertEqual(result['correlation_status'], 'PARTIAL_OR_CONTRADICTORY_EVIDENCE')
        self.assertIsNone(result['latest_matching_watchpoint_tick'])

    def test_wrong_watchpoint_value_cannot_claim_match(self):
        e = events()
        e[0]['after'] = '0x801E0004'
        self.assertFalse(self.analyze(e)['source_slot_write_agrees_with_a0'])

    def test_partial_overlapping_write_invalidates_full_prior_watch(self):
        e = events()
        e.insert(1, {'kind': 'watchpoint_write', 'tick': 150,
                     'address': '0x800D2EA1', 'width': 1,
                     'pc': '0x80012344', 'after': '0x12'})
        result = self.analyze(e)
        self.assertFalse(result['source_slot_write_agrees_with_a0'])
        self.assertIsNone(result['latest_matching_watchpoint_tick'])

    def test_irrelevant_disc_lba_cannot_claim_cdflr_correlation(self):
        e = events()
        e[2]['lba'] = 1000
        result = self.analyze(e)
        self.assertEqual(result['candidate_cdflr_range_read_count_before_snapshot'], 0)
        self.assertEqual(result['correlation_status'], 'PARTIAL_OR_CONTRADICTORY_EVIDENCE')

    def test_mutated_ram_never_passes(self):
        result = self.analyze(mutate_ram=True)
        self.assertEqual(result['correlation_status'], 'PARTIAL_OR_CONTRADICTORY_EVIDENCE')
        self.assertEqual(result['byte_comparison']['different_byte_count'], 1)

    def test_unordered_timestamps_rejected(self):
        e = events()
        e[2]['tick'] = 199
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            self.analyze(e)

    def test_snapshot_before_transfer_rejected(self):
        e = events()
        e[1]['kind'] = 'ram_snapshot'
        e[1].pop('a0')
        e[1].pop('a1')
        e[1].pop('a2')
        e[1].pop('target')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.analyze(e)

    def test_wrong_transfer_arguments_rejected(self):
        e = events()
        e[1]['a2'] = 1024
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.analyze(e)

    def test_duplicate_transfer_rejected(self):
        e = events()
        e.insert(2, dict(e[1], tick=220))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.analyze(e)

    def test_invalid_watchpoint_width_rejected(self):
        e = events()
        e[0]['width'] = 8
        with self.assertRaisesRegex(ValueError, 'watchpoint width'):
            self.analyze(e)

    def test_invalid_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.analyze(schema=2)

    def test_unknown_event_kind_rejected(self):
        e = events()
        e[2]['kind'] = 'imaginary_disk_success'
        with self.assertRaisesRegex(ValueError, 'unexpected kind'):
            self.analyze(e)


if __name__ == '__main__':
    unittest.main()
