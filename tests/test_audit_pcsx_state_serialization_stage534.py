"""Synthetic-only tests for the PCSX-Redux savestate diff classifier."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_pcsx_state_serialization_stage534 import audit_pair


def varint(value):
    out = bytearray()
    while value > 0x7f:
        out.append((value & 0x7f) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def field_varint(number, value):
    return varint((number << 3) | 0) + varint(value)


def field_bytes(number, value):
    return varint((number << 3) | 2) + varint(len(value)) + value


def state(payload, payload_size=1, payload_index=1, value=1, duplicate_field=False):
    fields = [field_bytes(1, payload), field_varint(2, value), field_varint(3, 1),
              field_varint(4, 1), field_varint(5, 1), field_varint(6, payload_size),
              field_varint(7, payload_index)]
    if duplicate_field:
        fields.append(field_varint(2, value))
    queue = b"".join(fields)
    cdrom = field_bytes(46, queue)
    info = field_bytes(1, b"PCSX-Redux SaveState v5") + field_varint(2, 5)
    return field_bytes(1, info) + field_bytes(15, cdrom)


class Stage534StateDiffTests(unittest.TestCase):
    def compare(self, before, after):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "before.state"
            b = Path(td) / "after.state"
            a.write_bytes(before)
            b.write_bytes(after)
            return audit_pair(a, b)

    def test_classifies_differences_only_in_unused_payload_tail(self):
        before = bytearray(range(16))
        after = bytearray(before)
        after[8] ^= 0x55
        after[9] ^= 0x22
        result = self.compare(state(bytes(before)), state(bytes(after)))
        self.assertEqual(result["status"], "PASS_DIFFS_ONLY_IN_UNUSED_CDRom_RESPONSEFIFO0_PAYLOAD_TAIL")
        self.assertEqual(result["changed_byte_count"], 2)
        self.assertEqual(result["changed_payload_indices"], [8, 9])
        self.assertEqual(result["payload_size"], 1)
        self.assertEqual(result["payload_index"], 1)
        self.assertTrue(result["active_payload_prefix_equal"])
        self.assertTrue(result["response_fifo_metadata_equal"])

    def test_active_payload_difference_rejected(self):
        before = bytearray(range(16))
        after = bytearray(before)
        after[0] ^= 1
        with self.assertRaisesRegex(ValueError, "active response FIFO payload prefix differs"):
            self.compare(state(bytes(before)), state(bytes(after)))

    def test_difference_in_queue_metadata_rejected(self):
        payload = bytes(range(16))
        with self.assertRaisesRegex(ValueError, "escapes unused response FIFO payload tail"):
            self.compare(state(payload, value=1), state(payload, value=2))

    def test_payload_size_change_rejected(self):
        before = bytearray(range(16))
        after = bytearray(before)
        after[8] ^= 1
        with self.assertRaisesRegex(ValueError, "active response FIFO size/index differ"):
            self.compare(state(bytes(before), payload_size=1), state(bytes(after), payload_size=10))

    def test_identical_states_rejected(self):
        payload = bytes(range(16))
        with self.assertRaisesRegex(ValueError, "no savestate serialization difference"):
            self.compare(state(payload), state(payload))

    def test_truncated_protobuf_rejected(self):
        info = field_bytes(1, field_bytes(1, b"PCSX-Redux SaveState v5") + field_varint(2, 5))
        with self.assertRaisesRegex(ValueError, "protobuf length-delimited field exceeds message"):
            self.compare(info + b"\x7a\x10\x01", info + b"\x7a\x10\x02")

    def test_duplicate_queue_field_rejected(self):
        payload = bytearray(range(16))
        altered = bytearray(payload)
        altered[8] ^= 1
        with self.assertRaisesRegex(ValueError, "unexpected CD-ROM response FIFO queue schema"):
            self.compare(state(bytes(altered), duplicate_field=True), state(bytes(payload), duplicate_field=True))

    def test_wrong_savestate_version_rejected(self):
        payload = bytes(range(16))
        malformed = field_bytes(1, field_bytes(1, b"PCSX-Redux SaveState v4") + field_varint(2, 4))
        malformed += field_bytes(15, field_bytes(46, field_bytes(1, payload) + field_varint(2, 1) +
                                               field_varint(3, 1) + field_varint(4, 1) +
                                               field_varint(5, 1) + field_varint(6, 1) + field_varint(7, 1)))
        other = bytearray(malformed)
        other[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "does not match the pinned PCSX-Redux v5"):
            self.compare(malformed, bytes(other))

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.state"
            link = root / "link.state"
            target.write_bytes(state(bytes(range(16))))
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "regular single-link file"):
                audit_pair(link, target)


if __name__ == "__main__":
    unittest.main()
