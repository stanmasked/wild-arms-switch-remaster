"""Stage437: ROM-free GP0 A0/80 palette upload chronology tests."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from audit_private_gp0_upload_timeline import (  # noqa: E402
    TRACE_KIND, VRAM_BYTES, MAX_TRACE_BYTES,
    audit_private_gp0_upload_timeline, read_private_gp0_timeline,
    replay_private_gp0_clut_timeline,
)

COLORS=struct.pack("<16H",0,31,992,31744,*([32767]*12))
BANK=COLORS+bytes(512-len(COLORS))
E6=[0xe6000000]


def clut(x=32,y=19):
    return (y<<6)|(x//16)


def vram(*, x=None, y=None):
    src=bytearray(VRAM_BYTES)
    if x is not None:
        offset=(y*1024+x)*2
        src[offset:offset+32]=COLORS
    return bytes(src)


def a0(raw, *, x=32,y=19,width=16,height=1):
    if len(raw) != 2*width*height:
        raise AssertionError("synthetic A0 pixel count error")
    payload=raw+(b"\x00\x00" if len(raw)%4 else b"")
    return [0xa0000000,(y<<16)|x,(height<<16)|width,
            *struct.unpack("<%dI"%(len(payload)//4),payload)]


def vram_copy(*,sx=32,sy=19,dx=64,dy=19,width=16,height=1):
    return [0x80000000,(sy<<16)|sx,(dy<<16)|dx,(height<<16)|width]


def polygon(*,x=32,y=19,page=0):
    c=clut(x,y)
    return [0x24000000,0,(c<<16)|0,0,(page<<16)|0,0,0]


def probe(packets, *, initial=None, banks=None, max_evidence=20000):
    return replay_private_gp0_clut_timeline(
        vram() if initial is None else initial,packets,
        [BANK] if banks is None else banks,frame=12,max_evidence=max_evidence)


def trace_header(raw=None,frame=12):
    return {"kind":TRACE_KIND,"schema":1,"frame":frame,
            "capture_phase":"before_first_packet",
            "initial_vram_sha256":hashlib.sha256(
                vram() if raw is None else raw).hexdigest()}


def write_trace(path, packets, *, initial=None, frame=12):
    hdr=trace_header(raw=initial,frame=frame)
    text=json.dumps(hdr)+"\n"
    for words in packets:
        text+=json.dumps({"frame":frame,"words":words})+"\n"
    Path(path).write_text(text,encoding="utf8")
    return hdr


class Stage437GP0TimelineTests(unittest.TestCase):
    def test_a0_upload_before_draw_fresh_clut_match(self):
        result=probe([E6,a0(COLORS),polygon()])
        self.assertEqual(result["counts"]["A0_CPU_TO_VRAM"],1)
        self.assertEqual(result["counts"]["4BPP_CLUT_DRAWS"],1)
        self.assertEqual(result["counts"]["4BPP_CLUT_MODELED_ROW_MATCHES_SOURCE"],1)
        self.assertEqual(result["counts"]["4BPP_CLUT_FULL_ROW_REWRITTEN_SINCE_LAST_DRAW"],1)
        event=result["clut_draw_events"][0]
        self.assertTrue(event["all_16_words_explicitly_written_since_previous_draw"])
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])
        self.assertEqual(event["clut_x_words"],32)
        self.assertEqual(event["row_sha256_before_draw"],hashlib.sha256(COLORS).hexdigest())

    def test_baseline_palette_can_match_but_is_not_fresh(self):
        result=probe([polygon()],initial=vram(x=32,y=19))
        event=result["clut_draw_events"][0]
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])
        self.assertFalse(event["all_16_words_explicitly_written_since_previous_draw"])

    def test_second_draw_without_new_upload_is_not_fresh(self):
        result=probe([E6,a0(COLORS),polygon(),polygon()])
        one,two=result["clut_draw_events"]
        self.assertTrue(one["all_16_words_explicitly_written_since_previous_draw"])
        self.assertFalse(two["all_16_words_explicitly_written_since_previous_draw"])
        self.assertEqual(result["counts"]["GPU_DRAW_PACKET_NOT_RASTERIZED"],2)

    def test_reupload_between_draws_restores_conditional_row_freshness(self):
        result=probe([E6,a0(COLORS),polygon(),a0(COLORS),polygon()])
        self.assertEqual([event["all_16_words_explicitly_written_since_previous_draw"]
                          for event in result["clut_draw_events"]],[True,True])

    def test_partial_palette_upload_is_never_full_row_proof(self):
        first=COLORS[:16]
        result=probe([E6,a0(first,width=8),polygon()],
                     initial=vram(x=32,y=19))
        self.assertFalse(result["clut_draw_events"][0][
            "all_16_words_explicitly_written_since_previous_draw"])

    def test_two_half_palette_uploads_complete_one_row(self):
        result=probe([E6,a0(COLORS[:16],width=8),
                      a0(COLORS[16:],x=40,width=8),polygon()])
        event=result["clut_draw_events"][0]
        self.assertTrue(event["all_16_words_explicitly_written_since_previous_draw"])
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])

    def test_nonoverlapping_vram_blit_preserves_tracked_copy_words(self):
        result=probe([E6,a0(COLORS),vram_copy(),polygon(x=64)])
        event=result["clut_draw_events"][0]
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])
        self.assertTrue(event["all_16_words_explicitly_written_since_previous_draw"])
        self.assertEqual(result["counts"]["80_VRAM_TO_VRAM"],1)

    def test_preexisting_source_blit_lacks_fresh_write_provenance(self):
        result=probe([E6,vram_copy(),polygon(x=64)],
                     initial=vram(x=32,y=19))
        event=result["clut_draw_events"][0]
        self.assertTrue(event["modeled_pre_draw_row_matches_candidate"])
        self.assertFalse(event["all_16_words_explicitly_written_since_previous_draw"])

    def test_blit_after_draw_from_stale_source_is_not_certified(self):
        result=probe([E6,a0(COLORS),polygon(),
                      vram_copy(),polygon(x=64)])
        self.assertFalse(result["clut_draw_events"][-1][
            "all_16_words_explicitly_written_since_previous_draw"])

    def test_odd_pixel_count_ignores_trailing_padding_halfword(self):
        raw=struct.pack("<3H",31,992,31744)
        result=probe([E6,a0(raw,x=32,y=19,width=3),polygon()])
        self.assertEqual(result["counts"]["A0_CPU_TO_VRAM"],1)
        self.assertFalse(result["clut_draw_events"][0][
            "all_16_words_explicitly_written_since_previous_draw"])

    def test_wrong_a0_payload_length_or_grid_bounds_rejected(self):
        broken=a0(COLORS)[:-1]
        for sequence in ([E6,broken],[E6,a0(COLORS,x=1016)],
                         [E6,[0xa0000000,0,0,42]]):
            with self.subTest(packet_count=len(sequence)),self.assertRaises(ValueError):
                probe(sequence)

    def test_vram_copy_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError,"overlapping"):
            probe([E6,vram_copy(dx=40)])

    def test_vram_copy_wrong_length_rejected(self):
        with self.assertRaisesRegex(ValueError,"four words"):
            probe([E6,vram_copy()[:-1]])

    def test_vram_copy_wrap_rejected(self):
        with self.assertRaisesRegex(ValueError,"wraps"):
            probe([E6,vram_copy(dx=1020)])

    def test_gpu_transfer_requires_explicit_e6_mask_state(self):
        for packet in (a0(COLORS),vram_copy()):
            with self.subTest(opcode=packet[0]),self.assertRaisesRegex(
                    ValueError,"prior explicit E6"):
                probe([packet])

    def test_e6_mask_1_or_2_rejected(self):
        for e6 in ([0xe6000001],[0xe6000002],[0xe6000003]):
            with self.subTest(mode=e6[0]),self.assertRaisesRegex(
                    ValueError,"write-mask"):
                probe([e6,a0(COLORS)])

    def test_unknown_gpu_line_command_fails_closed(self):
        # Stage522 models GP0(02) fill; unsupported line primitives still
        # must not be guessed or treated as a harmless state operation.
        with self.assertRaisesRegex(ValueError,"unknown GP0"):
            probe([[0x40000000,0,0]])
        with self.assertRaisesRegex(ValueError,"unknown GP0"):
            probe([E6,a0(COLORS),[0x40000000,0,0],polygon()])

    def test_texture_depth_not_four_bpp_skipped(self):
        report=probe([polygon(page=0x80)])
        self.assertEqual(report["counts"]["TEXTURED_NOT_4BPP"],1)
        self.assertEqual(report["clut_draw_events"],[])

    def test_evidence_limit_keeps_total_gpu_packet_counts(self):
        report=probe([polygon()]*3,max_evidence=1)
        self.assertEqual(len(report["clut_draw_events"]),1)
        self.assertEqual(report["counts"]["4BPP_CLUT_DRAWS"],3)
        self.assertEqual(report["counts"]["evidence_rows_truncated"],2)

    def test_all_zero_candidate_rows_skipped(self):
        report=probe([polygon()],initial=vram(),banks=[bytes(512)])
        self.assertEqual(report["candidate_eligible_distinct_rows"],0)
        self.assertFalse(report["clut_draw_events"][0]["modeled_pre_draw_row_matches_candidate"])

    def test_invalid_vram_banks_and_parameters_rejected(self):
        with self.assertRaises(ValueError):
            replay_private_gp0_clut_timeline(bytes(11),[],[BANK])
        with self.assertRaises(ValueError):
            probe([],banks=[bytes(511)])
        with self.assertRaises(ValueError):
            probe([],max_evidence=0)

    def test_jsonl_trace_pinned_to_before_frame_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"timeline.jsonl"
            write_trace(path,[E6,a0(COLORS),polygon()])
            h,packets,digest=read_private_gp0_timeline(
                path,hashlib.sha256(vram()).hexdigest())
            self.assertEqual(h["frame"],12)
            self.assertEqual(len(packets),3)
            self.assertEqual(len(digest),64)
            with self.assertRaisesRegex(ValueError,"header disagrees"):
                read_private_gp0_timeline(path,hashlib.sha256(bytes(VRAM_BYTES)).hexdigest()[:-1]+"0")

    def test_trace_bad_frame_duplicate_key_and_incomplete_jsonl(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"timeline.jsonl"
            hdr=trace_header()
            path.write_text(json.dumps(hdr)+"\n"+
                            json.dumps({"frame":13,"words":polygon()})+"\n")
            with self.assertRaises(ValueError):
                read_private_gp0_timeline(path,hdr["initial_vram_sha256"])
            path.write_text('{"schema":1,"schema":1}\n')
            with self.assertRaisesRegex(ValueError,"duplicate"):
                read_private_gp0_timeline(path,hdr["initial_vram_sha256"])
            path.write_text(json.dumps(hdr))
            with self.assertRaisesRegex(ValueError,"incomplete"):
                read_private_gp0_timeline(path,hdr["initial_vram_sha256"])

    def test_unsupported_trailing_packet_word_rejected(self):
        with self.assertRaises(ValueError):
            probe([polygon()+[1]])

    def test_private_entrypoint_with_synthetic_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            raw=root/"initial.u16le.bin"
            gp=root/"timeline.jsonl"
            raw.write_bytes(vram())
            write_trace(gp,[E6,a0(COLORS),polygon()])
            with patch("audit_private_gp0_upload_timeline.read_private_candidates",
                       return_value={"map_index":2,"candidate_banks":[BANK],
                                     "verified_streams":[]}):
                result=audit_private_gp0_upload_timeline(
                    root/"not-real-CDSTG.BIN",raw,gp)
            self.assertEqual(result["source_map_index"],2)
            self.assertTrue(result["clut_draw_events"][0][
                "all_16_words_explicitly_written_since_previous_draw"])
            self.assertEqual(len(result["private_trace_sha256"]),64)

    def test_metadata_contains_no_gpu_transfer_words_or_raw_palettes(self):
        report=probe([E6,a0(COLORS),polygon()])
        encoded=json.dumps(report)
        for forbidden in ('"words"','"vram_hex"','"source_palette_words"',
                          '"pixel_rgba"','"original_tiles"'):
            self.assertNotIn(forbidden,encoded)
        self.assertTrue(report["interpretation"][
            "actual_ps1_texture_and_clut_cache_semantics_unverified"])
        self.assertTrue(report["interpretation"][
            "gpu_framebuffer_drawing_not_rasterized"])


if __name__=="__main__":
    unittest.main()
