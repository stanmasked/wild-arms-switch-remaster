"""Synthetic-only Stage430 paused, double-read PS1 VRAM capture tests."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from capture_private_pcsx_redux_vram import RAW_VRAM_BYTES, DEFAULT_URL, verify_private_vram  # noqa: E402
from capture_private_stable_pcsx_vram import (  # noqa: E402
    FLOW_PATH, MAX_FLOW_RESPONSE, capture_stable_private_vram,
    read_private_pause_state,
)


def vram_bytes():
    return bytes(range(256)) * (RAW_VRAM_BYTES // 256)


class SyntheticHTTP:
    def __init__(self, data, *, url, status=200, actual_url=None):
        self.data = BytesIO(data)
        self.url = url if actual_url is None else actual_url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.data.close()

    def geturl(self):
        return self.url

    def read(self, count):
        return self.data.read(count)


class ScriptedOpener:
    def __init__(self, events):
        self.events = list(events)
        self.calls = []

    def open(self, request, timeout):
        assert request.get_method() == "GET"
        assert timeout == 10
        url = request.full_url
        self.calls.append(url)
        if not self.events:
            raise AssertionError("unexpected extra endpoint request")
        path, payload, options = self.events.pop(0)
        assert url == path, (url, path)
        return SyntheticHTTP(payload, url=url, **options)


FLOW_URL = "http://127.0.0.1:8080" + FLOW_PATH


def flow(running=False, *, payload=None, **options):
    return (FLOW_URL,
            json.dumps({"running": running}).encode("utf-8")
            if payload is None else payload, options)


def dump(data=None, **options):
    return (DEFAULT_URL, vram_bytes() if data is None else data, options)


def stable_script(*, first=None, second=None, statuses=(False, False, False)):
    return ScriptedOpener([
        flow(statuses[0]), dump(first), flow(statuses[1]),
        dump(second), flow(statuses[2]),
    ])


class Stage430StableCaptureTests(unittest.TestCase):
    def test_stable_capture_five_read_only_requests_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            opener = stable_script()
            report = capture_stable_private_vram(td, basename="stable01", opener=opener)
            self.assertEqual(opener.events, [])
            self.assertEqual(opener.calls, [FLOW_URL, DEFAULT_URL, FLOW_URL,
                                             DEFAULT_URL, FLOW_URL])
            self.assertTrue(report["two_read_bytes_identical"])
            self.assertTrue(report["api_reported_running_false_in_all_three_observations"])
            self.assertTrue(report["game_map_and_frame_number_unverified"])
            self.assertEqual(report["snapshot_read_count"], 2)
            self.assertEqual(report["execution_flow_read_count"], 3)
            self.assertTrue(verify_private_vram(td, basename="stable01")["verified"])
            self.assertEqual((Path(td)/"stable01.u16le.bin").read_bytes(), vram_bytes())

    def test_reject_running_before_first_capture(self):
        with tempfile.TemporaryDirectory() as td:
            opener = stable_script(statuses=(True, False, False))
            with self.assertRaisesRegex(ValueError, "running before"):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(opener.calls, [FLOW_URL])
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_reject_running_between_reads(self):
        with tempfile.TemporaryDirectory() as td:
            opener = stable_script(statuses=(False, True, False))
            with self.assertRaisesRegex(ValueError, "ran between"):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(opener.calls, [FLOW_URL,DEFAULT_URL,FLOW_URL])
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_reject_running_after_second_read(self):
        with tempfile.TemporaryDirectory() as td:
            opener = stable_script(statuses=(False, False, True))
            with self.assertRaisesRegex(ValueError, "resumed after"):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(len(opener.calls), 5)
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_reject_changed_vram_even_when_reported_paused(self):
        with tempfile.TemporaryDirectory() as td:
            changed = bytearray(vram_bytes())
            changed[7844] ^= 1
            opener = stable_script(second=bytes(changed))
            with self.assertRaisesRegex(ValueError, "two paused reads differ"):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_identical_nonzero_snapshot_is_not_frame_proof(self):
        with tempfile.TemporaryDirectory() as td:
            report = capture_stable_private_vram(td, opener=stable_script())
            self.assertTrue(report["emulator_was_paused_at_capture_unverified"])
            self.assertTrue(report["no_gp0_packet_trace_included"])
            self.assertTrue(report["not_evidence_of_runtime_clut_selection"])
            self.assertTrue(report["little_endian_word_order_assumed_not_independently_verified"])

    def test_malformed_execution_flow_rejected(self):
        for payload in (b"",b"not JSON",b"[]",b'{}',b'{"running": 1}',
                        b'{"running": "false"}',b'{"running": false, "running": false}',
                        b"\xff", b" "* (MAX_FLOW_RESPONSE+1)):
            with self.subTest(payload=payload[:40]):
                with self.assertRaises(ValueError):
                    read_private_pause_state(opener=ScriptedOpener([flow(payload=payload)]))

    def test_true_or_false_execution_flow(self):
        self.assertIs(read_private_pause_state(opener=ScriptedOpener([flow(True)])), True)
        self.assertIs(read_private_pause_state(opener=ScriptedOpener([flow(False)])), False)

    def test_flow_redirect_rejected(self):
        with self.assertRaisesRegex(ValueError,"redirected"):
            read_private_pause_state(opener=ScriptedOpener([
                flow(actual_url="http://evil.invalid/api/v1/execution-flow")]))

    def test_flow_http_error_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTP 200"):
            read_private_pause_state(opener=ScriptedOpener([flow(status=503)]))

    def test_refuse_external_host_before_contacting_opener(self):
        opener = stable_script()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "loopback"):
                capture_stable_private_vram(
                    td, url="http://example.com:8080/api/v1/gpu/vram/raw",
                    opener=opener)
        self.assertEqual(opener.calls, [])

    def test_existing_files_block_before_any_requests(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"surf_village_stable.capture.json"
            target.write_bytes(b"KEEP")
            opener=stable_script()
            with self.assertRaises(FileExistsError):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(target.read_bytes(), b"KEEP")
            self.assertEqual(opener.calls, [])

    def test_failed_vram_transfer_creates_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            opener=ScriptedOpener([flow(),dump(b"too short")])
            with self.assertRaisesRegex(ValueError,"1048576"):
                capture_stable_private_vram(td, opener=opener)
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_verify_detects_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            capture_stable_private_vram(td, opener=stable_script())
            target=Path(td)/"surf_village_stable.u16le.bin"
            with target.open("r+b") as fp:
                fp.seek(12345)
                fp.write(b"Z")
            with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
                verify_private_vram(td,basename="surf_village_stable")

    def test_two_distinct_basename_snapshots_do_not_replace_one_another(self):
        with tempfile.TemporaryDirectory() as td:
            first=capture_stable_private_vram(td,basename="read1",opener=stable_script())
            second=capture_stable_private_vram(td,basename="read2",opener=stable_script())
            self.assertEqual(first["vram_sha256"],second["vram_sha256"])
            self.assertEqual(len(list(Path(td).iterdir())),4)

    def test_reject_bad_label_basename_and_missing_directory(self):
        with tempfile.TemporaryDirectory() as td:
            for label in ("", "x"*161, 5):
                with self.subTest(label=label),self.assertRaises(ValueError):
                    capture_stable_private_vram(td,label=label,opener=stable_script())
            with self.assertRaises(ValueError):
                capture_stable_private_vram(td,basename="../escape",opener=stable_script())
            with self.assertRaises(ValueError):
                capture_stable_private_vram(Path(td)/"missing",opener=stable_script())


if __name__ == "__main__":
    unittest.main()
