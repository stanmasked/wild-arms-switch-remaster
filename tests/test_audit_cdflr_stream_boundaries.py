"""Synthetic-only CDFLR stream-marker, extent and token-grammar tests."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_cdflr_stream_boundaries import audit_streams, probe_flag_tokens  # noqa: E402

STRIDE = 8192


def make_slot(*, nonzero_trailer=False, marker_fault=None, bad_pointer=False):
    offsets = []
    pos = 256
    for index in range(58):
        offsets.append(pos)
        if index < 42:
            pos += 4
        elif index % 2 == 0:
            pos += 64
        else:
            pos += 128
    data = bytearray(STRIDE)
    for index, offset in enumerate(offsets):
        struct.pack_into("<I", data, index * 4, 0x80183000 + offset)
    if nonzero_trailer:
        data[232:256] = bytes(range(1, 25))
    for index in range(43, 58, 2):
        struct.pack_into("<I", data, offsets[index], 0x8000)
    if marker_fault is not None:
        struct.pack_into("<I", data, offsets[marker_fault], 0x12345678)
    if bad_pointer:
        struct.pack_into("<I", data, 56 * 4, 0x80183000 + offsets[55])
    return bytes(data)


def inspect(blob, output_hypothesis=32):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "fake-cdflr.bin"
        path.write_bytes(blob)
        return audit_streams(path, slot_bytes=STRIDE,
                             output_size_hypothesis=output_hypothesis)


class StreamBoundaryTests(unittest.TestCase):
    def test_all_eight_markers_per_slot_and_opaque_header(self):
        result = inspect(make_slot() + make_slot(nonzero_trailer=True))
        self.assertEqual(result["slot_count"], 2)
        self.assertEqual(result["candidate_stream_count"], 16)
        self.assertEqual(result["candidate_0x8000_marker_match_count"], 16)
        self.assertEqual(result["bounded_by_next_pointer_stream_count"], 14)
        self.assertEqual(result["candidate_marker_exception_sites"], [])
        self.assertEqual(result["last_stream_upper_bound_larger_than_output_hypothesis_slots"], [0, 1])
        self.assertTrue(result["interpretation"]["original_payload_bytes_emitted"] is False)

    def test_corrupted_marker_is_reported_not_accepted(self):
        result = inspect(make_slot(marker_fault=49))
        self.assertEqual(result["candidate_0x8000_marker_match_count"], 7)
        self.assertEqual(result["candidate_marker_exception_sites"], [
            {"slot_index": 0, "stream_index": 49}
        ])

    def test_last_stream_is_excluded_from_token_end_validation(self):
        result = inspect(make_slot())
        last = result["stream_profiles"][-1]
        self.assertTrue(last["is_last_unbounded_stream"])
        self.assertEqual(last["count"], 1)
        self.assertEqual(last["candidate_flag_tokens_truncated"], 0)
        self.assertEqual(last["candidate_flag_tokens_overshoot"], 0)
        self.assertEqual(last["candidate_flag_tokens_early_or_trailing"], 0)
        self.assertEqual(last["candidate_flag_tokens_near_boundary"], 0)

    def test_simple_flag_token_probe_is_not_a_decoder(self):
        literal = bytes.fromhex("00800000") + b"\xffabcdefgh"
        status, produced, consumed = probe_flag_tokens(literal, expected_output=8)
        self.assertEqual((status, produced, consumed),
                         ("NEAR_BOUNDARY", 8, len(literal)))
        status, _, _ = probe_flag_tokens(literal + b"four", expected_output=8)
        self.assertEqual(status, "EARLY_OR_TRAILING_DATA")
        status, _, _ = probe_flag_tokens(literal[:-2], expected_output=8)
        self.assertEqual(status, "TRUNCATED")
        # A reference token may exceed the requested output byte budget.
        oversized = bytes.fromhex("00800000") + bytes([0x00, 0x00, 0xF0])
        status, produced, _ = probe_flag_tokens(oversized, expected_output=8)
        self.assertEqual(status, "OUTPUT_OVERSHOOT")
        self.assertEqual(produced, 18)

    def test_bad_geometry_and_order_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            inspect(make_slot()[:-1])
        with self.assertRaisesRegex(ValueError, "ordering"):
            inspect(make_slot(bad_pointer=True))

    def test_invalid_candidate_output_budget_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "output_size_hypothesis"):
            inspect(make_slot(), output_hypothesis=0)

    def test_marker_value_does_not_prove_an_output_size(self):
        result = inspect(make_slot(), output_hypothesis=32)
        self.assertEqual(result["candidate_0x8000_marker_match_count"], 8)
        self.assertTrue(result["interpretation"]["0x8000_value_is_observed_not_verified_decompressed_size"])
        self.assertFalse(result["candidate_token_grammar"]["does_not_validate_back_references_or_produce_pixels"] is False)


if __name__ == "__main__":
    unittest.main()
