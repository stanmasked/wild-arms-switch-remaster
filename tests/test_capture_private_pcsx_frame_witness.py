"""Synthetic/ROM-free tests of owner-private VRAM/screen/disc capture witness."""
from io import BytesIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from capture_private_pcsx_redux_vram import DEFAULT_URL, RAW_VRAM_BYTES  # noqa: E402
from capture_private_pcsx_frame_witness import (  # noqa: E402
    DISC_PATH, MAX_SCREEN_BYTES, PNG_SIGNATURE, SCREEN_PATH,
    capture_private_frame_witness, read_private_disc_info,
    validate_private_png, verify_private_frame_witness,
)
from audit_surf_paused_vram_pair import read_verified_paused_capture  # noqa: E402

FLOW = "http://127.0.0.1:8080/api/v1/execution-flow"
SCREEN = "http://127.0.0.1:8080" + SCREEN_PATH
CD = "http://127.0.0.1:8080" + DISC_PATH


def fake_png(*, width=2, height=1):
    def chunk(kind, raw):
        return (struct.pack(">I", len(raw)) + kind + raw +
                struct.pack(">I", zlib.crc32(kind+raw) & 0xffffffff))
    ihdr = struct.pack(">IIBBBBB", width,height,8,6,0,0,0)
    pixels = b"\x00" + b"\xff\x00\x00\xff"*width
    return (PNG_SIGNATURE + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(pixels*height)) +
            chunk(b"IEND", b""))


def fake_vram():
    return bytes(range(256)) * (RAW_VRAM_BYTES//256)


class Reply:
    def __init__(self, url, payload, *, redirected=None, status=200):
        self.url=url if redirected is None else redirected
        self.body=BytesIO(payload)
        self.status=status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.body.close()
    def geturl(self):
        return self.url
    def read(self, length):
        return self.body.read(length)


class Sequence:
    def __init__(self, frames):
        self.frames=list(frames)
        self.calls=[]
    def open(self, req, timeout):
        self.calls.append(req.full_url)
        assert req.get_method()=="GET"
        assert timeout==10
        if not self.frames:
            raise AssertionError("unexpected extra HTTP request")
        expected_url,payload,options=self.frames.pop(0)
        assert req.full_url==expected_url, (req.full_url,expected_url)
        return Reply(req.full_url,payload,**options)


def flow(running=False, *, body=None, **options):
    return FLOW, (json.dumps({"running":running}).encode() if body is None
                  else body), options

def vram(raw=None, **options):
    return DEFAULT_URL, (fake_vram() if raw is None else raw), options

def image(png=None, **options):
    return SCREEN, (fake_png() if png is None else png), options

def cd(info=None, **options):
    return CD, (b'{"disc":"synthetic-CD"}' if info is None else info), options


def expected_sequence(*, statuses=(False,False,False,False),
                      first=None, second=None, png=None, disc=None):
    return Sequence([
        flow(statuses[0]),vram(first),flow(statuses[1]),
        image(png),cd(disc),flow(statuses[2]),vram(second),flow(statuses[3])
    ])


class Stage432FrameWitnessTests(unittest.TestCase):
    def test_complete_private_witness_and_verifier(self):
        with tempfile.TemporaryDirectory() as temp:
            result=capture_private_frame_witness(temp,basename="surf1",
                                                 opener=expected_sequence())
            self.assertEqual(result["execution_flow_read_count"],4)
            self.assertEqual(result["snapshot_read_count"],2)
            self.assertEqual(result["screen_dimensions"],{"width":2,"height":1})
            self.assertEqual(result["screen_bytes"],len(fake_png()))
            self.assertEqual(len(list(Path(temp).iterdir())),4)
            self.assertEqual((Path(temp)/"surf1.u16le.bin").read_bytes(),fake_vram())
            self.assertEqual((Path(temp)/"surf1.screen.png").read_bytes(),fake_png())
            self.assertEqual(verify_private_frame_witness(temp,basename="surf1")["verified"],True)
            assert len(result["screen_sha256"])==64

    def test_eight_read_only_local_requests_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            opener=expected_sequence()
            capture_private_frame_witness(temp,opener=opener)
            self.assertEqual(opener.calls,[
                FLOW,DEFAULT_URL,FLOW,SCREEN,CD,FLOW,DEFAULT_URL,FLOW])
            self.assertEqual(opener.frames,[])

    def test_paused_state_required_before_during_after(self):
        for i in range(4):
            with self.subTest(observation=i),tempfile.TemporaryDirectory() as temp:
                status=[False]*4
                status[i]=True
                with self.assertRaisesRegex(ValueError,"running|resumed"):
                    capture_private_frame_witness(temp,opener=expected_sequence(
                        statuses=tuple(status)))
                self.assertEqual(list(Path(temp).iterdir()),[])

    def test_vram_mutation_rejected_even_paused(self):
        altered=bytearray(fake_vram())
        altered[9999] ^= 0x20
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"VRAM changed"):
                capture_private_frame_witness(temp,opener=expected_sequence(
                    second=bytes(altered)))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_invalid_snapshot_byte_count(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"1048576"):
                capture_private_frame_witness(temp,opener=expected_sequence(
                    first=b"invalid"))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_corrupt_or_truncated_png_rejected(self):
        valid=fake_png()
        broken=bytearray(valid)
        broken[-9] ^= 0x80
        for data in (b"",b"hello",valid[:-1],bytes(broken),b"X"*100):
            with self.subTest(data=data[:16]),tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(ValueError):
                    capture_private_frame_witness(temp,opener=expected_sequence(png=data))
                self.assertEqual(list(Path(temp).iterdir()),[])

    def test_png_with_trailing_bytes_and_invalid_dimensions(self):
        with self.assertRaisesRegex(ValueError,"trailing bytes"):
            validate_private_png(fake_png()+b"MORE")
        with self.assertRaisesRegex(ValueError,"unsupported PNG"):
            validate_private_png(fake_png(width=0))

    def test_empty_invalid_duplicate_disc_info_rejected(self):
        for data in (b"",b"[]",b"{}",b"not JSON",b'{"x":1,"x":2}',b"\xff"):
            with self.subTest(value=data),self.assertRaises(ValueError):
                read_private_disc_info(data)

    def test_cd_info_can_be_non_game_specific_and_is_not_scene_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            info=b'{"name":"synthetic-not-Wild-Arms","injected":false}'
            result=capture_private_frame_witness(temp,opener=expected_sequence(disc=info))
            self.assertTrue(result["game_map_and_frame_number_unverified"])
            self.assertTrue(result["not_evidence_of_runtime_clut_selection"])
            self.assertTrue(result["no_gp0_packet_trace_included"])
            self.assertEqual((Path(temp)/"surf_village_frame_witness.cdinfo.json").read_bytes(),info)

    def test_reject_remote_endpoint_before_network(self):
        opener=expected_sequence()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"loopback"):
                capture_private_frame_witness(temp,
                    url="http://remote.invalid:8080/api/v1/gpu/vram/raw",
                    opener=opener)
            self.assertEqual(opener.calls,[])

    def test_redirect_and_http_errors_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            events=expected_sequence()
            events.frames[3]=image(redirected="http://remote.invalid")
            with self.assertRaisesRegex(ValueError,"redirected"):
                capture_private_frame_witness(temp,opener=events)
            self.assertEqual(list(Path(temp).iterdir()),[])
        with tempfile.TemporaryDirectory() as temp:
            events=expected_sequence()
            events.frames[4]=cd(status=502)
            with self.assertRaisesRegex(ValueError,"invalid or redirected"):
                capture_private_frame_witness(temp,opener=events)

    def test_no_clobber_any_of_four_files(self):
        names=("surf_village_frame_witness.u16le.bin",
               "surf_village_frame_witness.screen.png",
               "surf_village_frame_witness.cdinfo.json",
               "surf_village_frame_witness.capture.json")
        for filename in names:
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/filename
                path.write_bytes(b"KEEP")
                opener=expected_sequence()
                with self.assertRaises(FileExistsError):
                    capture_private_frame_witness(temp,opener=opener)
                self.assertEqual(opener.calls,[])
                self.assertEqual(path.read_bytes(),b"KEEP")

    def test_verify_detects_tampering_of_screen_or_disc_or_vram(self):
        for suffix in (".screen.png",".cdinfo.json",".u16le.bin"):
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as temp:
                capture_private_frame_witness(temp,basename="a",opener=expected_sequence())
                path=Path(temp)/("a"+suffix)
                with path.open("r+b") as file:
                    file.seek(9)
                    file.write(b"x")
                with self.assertRaisesRegex(ValueError,"hash mismatch"):
                    verify_private_frame_witness(temp,basename="a")

    def test_verify_rejects_path_traversal_in_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            capture_private_frame_witness(temp,opener=expected_sequence())
            path=Path(temp)/"surf_village_frame_witness.capture.json"
            manifest=json.loads(path.read_text())
            manifest["screen_filename"]="../elsewhere.png"
            path.write_text(json.dumps(manifest),encoding="utf8")
            with self.assertRaisesRegex(ValueError,"provenance"):
                verify_private_frame_witness(temp)

    def test_no_files_on_rollback_after_second_link_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            from capture_private_pcsx_frame_witness import os as target_os
            link=target_os.link
            count=[0]
            def fails(*args,**kwargs):
                count[0]+=1
                if count[0]==2:
                    raise OSError("synthetic linking interruption")
                return link(*args,**kwargs)
            with patch("capture_private_pcsx_frame_witness.os.link",
                       side_effect=fails):
                with self.assertRaisesRegex(OSError,"linking interruption"):
                    capture_private_frame_witness(temp,opener=expected_sequence())
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_reject_overlarge_png_response(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"too large"):
                capture_private_frame_witness(temp,
                    opener=expected_sequence(png=b"x"*(MAX_SCREEN_BYTES+1)))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_new_witness_can_feed_stage431_pair_comparator(self):
        with tempfile.TemporaryDirectory() as temp:
            capture_private_frame_witness(temp,basename="a",opener=expected_sequence())
            capture_private_frame_witness(temp,basename="b",opener=expected_sequence())
            for name in ("a","b"):
                entry=read_verified_paused_capture(temp,name)
                self.assertEqual(len(entry["bytes"]),RAW_VRAM_BYTES)


if __name__=="__main__":
    unittest.main()
