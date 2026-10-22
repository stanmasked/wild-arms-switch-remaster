"""Stage449 ROM-free exact roundtrip integrity of native GPU dump imports."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_private_pcsx_native_gpudump_import import (
    verify_private_native_import)
from import_private_pcsx_native_gpudump import (
    GAME_ID,GP0,TRACE_BEGIN,import_private_native_gpudump)
from test_import_private_pcsx_native_gpudump import (
    base_records, dump_bytes,files)

ID="SLUS-12345"


def valid_game_id_words(game_id=ID):
    original=game_id.encode("ascii")+b"\0"
    original+=bytes((-len(original))%4)
    return list(struct.unpack("<%dI"%(len(original)//4),original))


def prepared(directory, *,records=None,frame=449):
    rec=base_records() if records is None else records
    if any(k==GAME_ID for k,_ in rec):
        position=next(i for i,(k,_) in enumerate(rec) if k==GAME_ID)
        rec[position]=(GAME_ID,valid_game_id_words())
    native, pre, trace=files(directory,dump_bytes(rec))
    import_private_native_gpudump(native,pre,trace,frame=frame)
    return native,pre,trace


class Stage449ImportIntegrityTests(unittest.TestCase):
    def test_exact_native_dump_to_vram_and_all_gp0_words(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            result=verify_private_native_import(
                native,pre,trace,expected_frame=449,
                expected_native_game_id=ID,
                expected_native_sha256=hashlib.sha256(native.read_bytes()).hexdigest())
            self.assertTrue(result["all_saved_gp0_packet_words_equal_native_first_frame"])
            self.assertTrue(result["all_saved_prepacket_vram_bytes_equal_native_snapshot"])
            self.assertEqual(result["exact_gp0_packet_count_verified"],8)
            self.assertEqual(result["exact_preframe_vram_bytes_verified"],1048576)
            self.assertTrue(result["independently_expected_game_id_compared"])
            self.assertTrue(result["independently_expected_dump_digest_compared"])

    def test_no_external_game_identity_is_not_implied_by_self_consistency(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            result=verify_private_native_import(native,pre,trace)
            self.assertTrue(result["game_id_present_in_native_preamble"])
            self.assertFalse(result["independently_expected_game_id_compared"])
            self.assertTrue(result["recorded_first_frame_does_not_authenticate_surf_village_scene"])
            self.assertTrue(result["operator_expected_game_id_not_authentication_of_original_disc"])

    def test_expected_game_id_mismatch_refused_without_exposing_native_id(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"differs from caller"):
                verify_private_native_import(native,pre,trace,
                    expected_native_game_id="SLUS-OTHER")

    def test_expected_raw_dump_hash_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            with self.assertRaisesRegex(ValueError,"independent SHA256"):
                verify_private_native_import(
                    native,pre,trace,expected_native_sha256="a"*64)

    def test_invalid_game_id_input_and_digest_refused(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            for ident in ("","WITH SPACES",True,"\0"):
                with self.subTest(identity=ident),self.assertRaisesRegex(ValueError,"ASCII"):
                    verify_private_native_import(native,pre,trace,
                                                 expected_native_game_id=ident)
            for digest in ("BAD",b"0"*64,"A"*64):
                with self.subTest(digest=digest),self.assertRaisesRegex(ValueError,"lowercase"):
                    verify_private_native_import(native,pre,trace,
                                                 expected_native_sha256=digest)
            with self.assertRaisesRegex(ValueError,"nonnegative"):
                verify_private_native_import(native,pre,trace,expected_frame=True)

    def test_changed_vram_byte_detected_even_when_file_size_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            original=bytearray(pre.read_bytes())
            original[5431]^=1
            pre.write_bytes(original)
            with self.assertRaisesRegex(ValueError,"VRAM differs|header disagrees"):
                verify_private_native_import(native,pre,trace)

    def test_modified_gp0_packet_word_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            lines=trace.read_text().splitlines()
            event=json.loads(lines[-1])
            event["words"][-1]^=1
            lines[-1]=json.dumps(event)
            trace.write_text("\n".join(lines)+"\n")
            with self.assertRaisesRegex(ValueError,"packet differs"):
                verify_private_native_import(native,pre,trace)

    def test_omitted_gp0_packet_detected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            lines=trace.read_text().splitlines()
            trace.write_text("\n".join(lines[:-1])+"\n")
            with self.assertRaisesRegex(ValueError,"packet count differs"):
                verify_private_native_import(native,pre,trace)

    def test_jsonl_from_other_capture_rejected_even_if_same_initial_vram(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            first=root/"first";first.mkdir()
            second=root/"second";second.mkdir()
            native,pre,trace=prepared(first)
            altered=base_records()
            words=list(altered[-2][1])
            words[-1]^=1
            altered[-2]=(GP0,words)
            _,_,other_trace=prepared(second,records=altered)
            trace.write_bytes(other_trace.read_bytes())
            with self.assertRaisesRegex(ValueError,"packet differs"):
                verify_private_native_import(native,pre,trace)

    def test_missing_gameid_requires_explicit_id_not_implicit_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            rec=[item for item in base_records() if item[0]!=GAME_ID]
            native,pre,trace=prepared(td,records=rec)
            verified=verify_private_native_import(native,pre,trace)
            self.assertFalse(verified["game_id_present_in_native_preamble"])
            with self.assertRaisesRegex(ValueError,"differs"):
                verify_private_native_import(native,pre,trace,
                                             expected_native_game_id=ID)

    def test_duplicate_native_gameid_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rec=base_records()
            rec.insert(2,(GAME_ID,valid_game_id_words()))
            native,pre,trace=prepared(td,records=rec)
            with self.assertRaisesRegex(ValueError,"unique GameID"):
                verify_private_native_import(native,pre,trace)

    def test_game_id_without_null_padding_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            rec=base_records()
            native,pre,trace=prepared(td,records=rec)
            # Rebuild the capture with the unpadded four-letter fake ID
            native.write_bytes(dump_bytes(base_records()))
            with self.assertRaisesRegex(ValueError,"zero-padded"):
                verify_private_native_import(native,pre,trace)

    def test_gameid_after_trace_begin_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            rec=base_records()
            rec[1]=(GAME_ID,valid_game_id_words())
            rec.insert(-1,(GAME_ID,valid_game_id_words()))
            native.write_bytes(dump_bytes(rec))
            with self.assertRaisesRegex(ValueError,"preamble-only"):
                verify_private_native_import(native,pre,trace)

    def test_expected_frame_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td,frame=9)
            with self.assertRaisesRegex(ValueError,"frame differs"):
                verify_private_native_import(native,pre,trace,expected_frame=10)

    def test_rejects_symlinked_vram_or_aliased_original(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            link=Path(td)/"prelink.u16le"
            link.symlink_to(pre)
            with self.assertRaisesRegex(ValueError,"aliased owner-private"):
                verify_private_native_import(native,link,trace)
            with self.assertRaisesRegex(ValueError,"aliased owner-private"):
                verify_private_native_import(native,native,trace)

    def test_partial_jsonl_newline_rejected_by_stage437_validator(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            trace.write_bytes(trace.read_bytes().rstrip(b"\n"))
            with self.assertRaisesRegex(ValueError,"incomplete or excessive"):
                verify_private_native_import(native,pre,trace)

    def test_report_never_contains_gameid_or_native_payload_words(self):
        with tempfile.TemporaryDirectory() as td:
            native,pre,trace=prepared(td)
            report=verify_private_native_import(
                native,pre,trace,expected_native_game_id=ID)
            encoded=json.dumps(report)
            for forbidden in (ID,'"game_id_string"','"raw_gpu_words"',
                              '"original_palette_u16"','"vram_payload"'):
                self.assertNotIn(forbidden,encoded)
            self.assertTrue(report["all_hashes_and_report_must_remain_owner_private"])
            self.assertTrue(report["no_native_game_id_gpu_pixels_packet_words_or_vram_emitted"])


if __name__=="__main__":
    unittest.main()
