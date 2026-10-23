"""Stage447 ROM-free native PSXGPUDUMPv1r1 capture/VRAM importer tests."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from import_private_pcsx_native_gpudump import (
    MAGIC, FULL_VRAM_A0_WORDS, GP0, GP1, VSYNC, READBACK,
    TRACE_BEGIN, GPU_VERSION, GAME_ID,
    read_native_gpu_dump, select_first_native_gp0_frame,
    import_private_native_gpudump)
from audit_private_gp0_upload_timeline import (
    VRAM_BYTES, read_private_gp0_timeline)
from test_audit_private_gp0_upload_timeline import (
    COLORS, E6, a0, polygon)

RESTORE=[0xe1000000,0xe2000000,0xe3000000,
         0xe4000000,0xe5000000,0xe6000000]
FULL=[0xa0000000,0,0x02000400]+[0]*(VRAM_BYTES//4)

def native_record(kind,words=()):
    return (struct.pack("<I",(kind<<24)|len(words))
            + (struct.pack("<%dI"%len(words),*words) if words else b""))

def base_records(*,live=None,init=None):
    return [
        (GPU_VERSION,[2]),
        (GAME_ID,[0x53554c53]),  # invented four ASCII bytes, not a real serial.
        (GP1,[0]),
        (GP0,FULL if init is None else init),
        (GP0,RESTORE),
        (GP1,[0x03000000,0x08000000]),
        (TRACE_BEGIN,[]),
        (GP0,[*a0(COLORS),*polygon()] if live is None else live),
        (VSYNC,[1234,0]),
    ]

def dump_bytes(records=None):
    return MAGIC+b"".join(native_record(kind,words)
                         for kind,words in (
                             base_records() if records is None else records))

def files(folder,data=None):
    root=Path(folder)
    src=root/"native.gpudump"
    src.write_bytes(dump_bytes() if data is None else data)
    pre=root/"before.u16le.bin"
    trace=root/"frame.jsonl"
    return src,pre,trace

class Stage447NativeDumpTests(unittest.TestCase):
    def test_imports_first_frame_and_exact_full_vram_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td)
            result=import_private_native_gpudump(src,pre,trace,frame=47)
            self.assertEqual(pre.stat().st_size,VRAM_BYTES)
            self.assertEqual(pre.read_bytes(),bytes(VRAM_BYTES))
            self.assertEqual(result["bootstrap_state_gp0_word_count"],6)
            self.assertEqual(result["live_frame_gp0_word_count"],
                             len(a0(COLORS))+len(polygon()))
            self.assertEqual(result["first_frame_model_packet_count"],8)
            self.assertEqual(result["native_total_completed_vsync_count"],1)
            hdr,packets,digest=read_private_gp0_timeline(
                trace,hashlib.sha256(pre.read_bytes()).hexdigest())
            self.assertEqual(hdr["frame"],47)
            self.assertEqual([p[0] for p in packets[:6]],RESTORE)
            self.assertEqual(packets[6:],[a0(COLORS),polygon()])
            self.assertEqual(digest,result["modeled_trace_sha256"])
            if os.name != "nt":
                self.assertEqual(pre.stat().st_mode & 0o777,0o600)
                self.assertEqual(trace.stat().st_mode & 0o777,0o600)

    def test_initial_vram_nonzero_word_preserved_exactly(self):
        changed=list(FULL)
        changed[3+55]=0x1234abcd
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td,dump_bytes(base_records(init=changed)))
            import_private_native_gpudump(src,pre,trace)
            self.assertEqual(pre.read_bytes()[55*4:55*4+4],b"\xcd\xab\x34\x12")

    def test_multiple_native_gp0_transport_records_combine_into_one_a0(self):
        rec=base_records()
        # Replace the live GP0 record with two native transport pieces
        # while preserving raw GP0 chronological word order.
        idx=7
        cmd=rec[idx][1]
        rec[idx:idx+1]=[(GP0,cmd[:5]),(GP0,cmd[5:])]
        selected=select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))
        self.assertEqual(selected["actual_live_gp0_record_count"],2)
        self.assertEqual(selected["modeled_packet_counts"]["A0_UPLOAD"],1)

    def test_only_first_vsync_interval_chosen_even_if_later_frames_present(self):
        rec=base_records()
        rec.extend([(GP0,[0x00000000]),(VSYNC,[2345,0])])
        selected=select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))
        self.assertEqual(selected["recorded_vsync_count"],2)
        self.assertEqual(selected["live_gp0_word_count"],
                         len(a0(COLORS))+len(polygon()))

    def test_bad_magic_refused(self):
        with self.assertRaisesRegex(ValueError,"PSXGPUDUMP"):
            read_native_gpu_dump(b"BAD-NATIVE-HEADER"+dump_bytes()[16:])

    def test_truncated_native_word_refused(self):
        with self.assertRaises(ValueError):
            read_native_gpu_dump(dump_bytes()[:-1])

    def test_corrupt_native_packet_length_refused(self):
        data=bytearray(dump_bytes())
        struct.pack_into("<I",data,16,(GPU_VERSION<<24)|0x200)
        with self.assertRaisesRegex(ValueError,"truncated or excessive"):
            read_native_gpu_dump(bytes(data[:40]))

    def test_unknown_native_record_kind_refused(self):
        with self.assertRaisesRegex(ValueError,"record kind"):
            read_native_gpu_dump(MAGIC+native_record(0xfe,[1]))

    def test_native_version_must_be_two(self):
        rec=base_records()
        rec[0]=(GPU_VERSION,[3])
        with self.assertRaisesRegex(ValueError,"version 2"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_native_reset_must_precede_full_vram(self):
        rec=base_records()
        rec[2]=(GP1,[0x08000000])
        with self.assertRaisesRegex(ValueError,"GPU GP1 reset"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_initial_full_vram_header_and_dimensions_checked(self):
        broken=list(FULL)
        broken[2]=0x01000400
        with self.assertRaisesRegex(ValueError,"full 1024x512"):
            select_first_native_gp0_frame(
                read_native_gpu_dump(dump_bytes(base_records(init=broken))))

    def test_malformed_initial_gpu_restore_order_refused(self):
        rec=base_records()
        rec[4]=(GP0,list(reversed(RESTORE)))
        with self.assertRaisesRegex(ValueError,"ordered GP0"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_missing_tracebegin_refused(self):
        rec=[x for x in base_records() if x[0]!=TRACE_BEGIN]
        with self.assertRaises(ValueError):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_missing_vsync_refused_as_incomplete_frame(self):
        rec=base_records()[:-1]
        with self.assertRaisesRegex(ValueError,"completed first live frame"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_live_gp1_state_changes_rejected_by_old_replayer(self):
        rec=base_records()
        rec.insert(-1,(GP1,[0x08000001]))
        with self.assertRaisesRegex(ValueError,"unsupported live GP1"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_identical_display_controls_do_not_change_first_frame_gp0(self):
        original=select_first_native_gp0_frame(
            read_native_gpu_dump(dump_bytes(base_records())))
        rec=base_records()
        rec.insert(-1,(GP1,[0x03000000,0x08000000,0x03000000]))
        replay=select_first_native_gp0_frame(
            read_native_gpu_dump(dump_bytes(rec)))
        self.assertEqual(replay["idempotent_live_gp1_control_word_count"],3)
        self.assertEqual(replay["modeled_gp0_raw"],original["modeled_gp0_raw"])
        self.assertEqual(replay["initial_vram"],original["initial_vram"])

    def test_full_control_state_restore_allows_exact_redundant_live_controls(self):
        rec=base_records()
        rec[5]=(GP1,[0x03000000,0x08000027,0x05000000,0x04000002])
        rec.insert(-1,(GP1,[0x05000000,0x04000002,0x03000000,0x04000002]))
        accepted=select_first_native_gp0_frame(
            read_native_gpu_dump(dump_bytes(rec)))
        self.assertEqual(accepted["idempotent_live_gp1_control_word_count"],4)
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td,dump_bytes(rec))
            report=import_private_native_gpudump(src,pre,trace)
            self.assertEqual(report["native_live_idempotent_gp1_word_count"],4)
            self.assertTrue(report["native_live_gp1_control_state_changes_rejected"])
            self.assertFalse(report["gpu_gp1_and_readback_unmodeled_live_events_rejected"])

    def test_unobserved_gp1_control_rejected_even_when_syntactically_safe(self):
        rec=base_records()
        rec.insert(-1,(GP1,[0x04000002]))
        with self.assertRaisesRegex(ValueError,"unsupported live GP1"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_duplicate_native_gp1_restore_provenance_rejected(self):
        rec=base_records()
        rec[5]=(GP1,[0x03000000,0x03000000,0x08000000])
        with self.assertRaisesRegex(ValueError,"ambiguous duplicate native pretrace GP1"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_gp1_side_effects_not_treated_as_idempotent(self):
        for word in (0x00000000,0x01000000,0x02000000,0x10000000):
            rec=base_records()
            rec.insert(-1,(GP1,[word]))
            with self.subTest(word=word):
                with self.assertRaisesRegex(ValueError,"unsupported live GP1"):
                    select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_redundant_controls_followed_by_actual_mode_change_rejected(self):
        rec=base_records()
        rec.insert(-1,(GP1,[0x03000000,0x08000001]))
        with self.assertRaisesRegex(ValueError,"unsupported live GP1"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_live_gpu_readback_rejected(self):
        rec=base_records()
        rec.insert(-1,(READBACK,[1]))
        with self.assertRaisesRegex(ValueError,"unsupported live GP1/readback"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_live_unsupported_gp0_opcode_rejected(self):
        rec=base_records(live=[0x02000000,0,0])
        with self.assertRaisesRegex(ValueError,"unsupported GP0 opcode"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_live_a0_truncated_in_native_transport_is_rejected(self):
        rec=base_records(live=a0(COLORS)[:-1])
        with self.assertRaisesRegex(ValueError,"incomplete final GP0 packet"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_duplicate_tracebegin_rejected(self):
        rec=base_records()
        rec.insert(-1,(TRACE_BEGIN,[]))
        with self.assertRaisesRegex(ValueError,"TraceBegin"):
            select_first_native_gp0_frame(read_native_gpu_dump(dump_bytes(rec)))

    def test_private_import_does_not_overwrite_existing_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td)
            trace.write_bytes(b"KEEP")
            with self.assertRaises(ValueError):
                import_private_native_gpudump(src,pre,trace)
            self.assertEqual(trace.read_bytes(),b"KEEP")
            self.assertFalse(pre.exists())

    def test_native_dump_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td)
            link=Path(td)/"link.gpudump"
            link.symlink_to(src)
            with self.assertRaisesRegex(ValueError,"unsafe native"):
                import_private_native_gpudump(link,pre,trace)

    def test_metadata_never_exposes_original_gp0_or_vram_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            src,pre,trace=files(td)
            result=import_private_native_gpudump(src,pre,trace)
            encoded=json.dumps(result)
            for forbidden in ('"raw_original_palette_words"',
                              '"gpu_payload_bytes"','"disc_bin"',
                              '"original_pixels"','"game_id"'):
                self.assertNotIn(forbidden,encoded)
            self.assertTrue(result["all_native_game_data_and_hashes_remain_owner_private"])
            self.assertTrue(result["only_first_native_frame_selected"])

if __name__=="__main__":
    unittest.main()
