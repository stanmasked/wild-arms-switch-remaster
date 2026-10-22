"""Stage455: synthetic pinned PCSX GPU Dump Player snapshot reader and GUI patch."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_private_gpudump_player_step1_export import (
    MAGIC,HEADER,VRAM_BYTES,parse_private_detached_step1_snapshot,
    verify_private_detached_step1_export,
)
from patch_private_pcsx_gpudump_player_step1_export import (
    PINNED, patched_header, patched_source, make_diff, replace_once,
)
from test_verify_private_pcsx_native_gpudump_import import prepared
from test_verify_private_gpudump_player_rewind_rgb import png


def snapshot(payload,*,frame=1,magic=MAGIC,declared=None,checksum=None):
    if declared is None: declared=len(payload)
    if checksum is None: checksum=zlib.crc32(payload)&0xffffffff
    return HEADER.pack(magic,frame,declared,checksum)+payload


def fixture(root,*,color=0,screen_rgb=None):
    native,pre,trace=prepared(Path(root))
    data=bytearray(pre.read_bytes())
    if color:
        data[0:2]=color.to_bytes(2,"little")
        data[2:4]=color.to_bytes(2,"little")
    file=Path(root)/"private-step1.wa1step.bin"
    file.write_bytes(snapshot(data))
    picture=Path(root)/"step1.png"
    if screen_rgb is None:
        screen_rgb=(248,0,0) if color&0x7fff==31 else (0,0,0)
    picture.write_bytes(png(screen_rgb))
    return native,pre,trace,file,picture


def audit(paths,**opts):
    return verify_private_detached_step1_export(
        *paths,x=0,y=0,width=2,height=1,**opts)


class Stage455ReaderTests(unittest.TestCase):
    def test_magic_is_fixed_exactly_16_bytes(self):
        self.assertEqual(len(MAGIC),16)
        self.assertEqual(HEADER.size,32)

    def test_frame_and_crc_are_verified_from_same_binary(self):
        data=bytes(VRAM_BYTES)
        record=parse_private_detached_step1_snapshot(snapshot(data))
        self.assertEqual(record["frame"],1)
        self.assertEqual(record["raw"],data)
        self.assertTrue(record["crc32_verified"])

    def test_rejects_partial_or_extra_snapshot_bytes(self):
        binary=snapshot(bytes(VRAM_BYTES))
        for modified in (binary[:-1],binary+b"0",binary[:20],b""):
            with self.subTest(length=len(modified)),self.assertRaisesRegex(
                    ValueError,"exactly"):
                parse_private_detached_step1_snapshot(modified)

    def test_rejects_bad_magic(self):
        with self.assertRaisesRegex(ValueError,"magic"):
            parse_private_detached_step1_snapshot(
                snapshot(bytes(VRAM_BYTES),magic=b"x"*16))

    def test_rejects_rewind_and_second_step_frames(self):
        for frame in (0,2,3,2**64-1):
            with self.subTest(frame=frame),self.assertRaisesRegex(
                    ValueError,"not from Player Frame 1"):
                parse_private_detached_step1_snapshot(
                    snapshot(bytes(VRAM_BYTES),frame=frame))

    def test_rejects_false_declared_vram_length(self):
        with self.assertRaisesRegex(ValueError,"declared"):
            parse_private_detached_step1_snapshot(
                snapshot(bytes(VRAM_BYTES),declared=VRAM_BYTES-2))

    def test_rejects_corrupted_payload_without_trusting_png(self):
        binary=bytearray(snapshot(bytes(VRAM_BYTES)))
        binary[-3]^=1
        with self.assertRaisesRegex(ValueError,"CRC32 mismatch"):
            parse_private_detached_step1_snapshot(bytes(binary))

    def test_rejects_corrupted_crc_field(self):
        with self.assertRaisesRegex(ValueError,"CRC32 mismatch"):
            parse_private_detached_step1_snapshot(
                snapshot(bytes(VRAM_BYTES),checksum=1))

    def test_full_native_dump_bound_and_snapshot_png_match(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=31)
            r=audit(p,expected_frame=449)
            self.assertTrue(r["roi_exact_rgb_equal"])
            self.assertEqual(r["exported_player_frame_from_container"],1)
            self.assertEqual(r["exported_vram_byte_count"],VRAM_BYTES)
            self.assertEqual(r["change_from_native_pretrace"][
                "roi_visibly_changed_rgb555_pixel_count"],2)
            self.assertEqual(r["status"],
                "PATCHED_PLAYER_STEP1_CONTAINER_RGB_EQUALITY_DUMP_LINK_UNVERIFIED")

    def test_native_dump_does_not_derive_export_source_identity(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            r=audit(p)
            self.assertTrue(r["interpretation"][
                "container_does_not_authenticate_loaded_native_dump_identity"])
            self.assertTrue(r["interpretation"][
                "patched_player_build_is_not_attested_by_this_tool"])

    def test_bit15_only_changes_do_not_count_as_visible(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=0x8000)
            r=audit(p)
            self.assertEqual(r["change_from_native_pretrace"][
                "roi_visibly_changed_rgb555_pixel_count"],0)
            self.assertEqual(r["change_from_native_pretrace"][
                "roi_changed_u16_halfword_count"],2)

    def test_opt_in_changes_requirement_can_fail_static_roi(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            with self.assertRaisesRegex(ValueError,"no visible change"):
                audit(p,require_changed_roi=True)

    def test_false_old_png_does_not_validate_step_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=31,screen_rgb=(0,0,0))
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                audit(p)
            r=audit(p,require_exact_rgb=False)
            self.assertEqual(r["status"],
                "PATCHED_PLAYER_STEP1_CONTAINER_RGB_MISMATCH_NO_VISUAL_BINDING")

    def test_file_sha_expectations_are_independently_checked(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            digest=hashlib.sha256(p[3].read_bytes()).hexdigest()
            pngsha=hashlib.sha256(p[4].read_bytes()).hexdigest()
            r=audit(p,expected_snapshot_sha256=digest,
                    expected_png_sha256=pngsha)
            self.assertEqual(r["exported_snapshot_file_sha256"],digest)
            with self.assertRaisesRegex(ValueError,"independent SHA-256"):
                audit(p,expected_snapshot_sha256="f"*64)

    def test_invalid_digests_and_strict_mode_types_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            for opts in (
                    {"expected_png_sha256":"XYZ"},
                    {"expected_snapshot_sha256":True},
                    {"require_exact_rgb":1},
                    {"require_changed_roi":"yes"}):
                with self.subTest(opts=opts),self.assertRaises(ValueError):
                    audit(p,**opts)

    def test_public_report_contains_no_original_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            r=audit(fixture(root,color=31))
            text=json.dumps(r)
            for name in ('"raw_gp0_words"','"real_disc_data"',
                         '"raw_vram_u16"','"exported_rgba_pixels"'):
                self.assertNotIn(name,text)
            self.assertTrue(r["interpretation"]["all_hashes_and_reports_remain_owner_private"])

    def test_symlink_and_alias_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            link=Path(root)/"step-link"
            link.symlink_to(p[3])
            with self.assertRaisesRegex(ValueError,"aliased"):
                audit((*p[:3],link,p[4]))
            with self.assertRaisesRegex(ValueError,"aliased"):
                audit((*p[:3],p[1],p[4]))


HEADER_SNIPPET="""    FileDialog<FileDialogMode::Save> m_saveDialog;
    FileDialog<FileDialogMode::Open> m_openDialog;
    GLuint m_texture = 0;
    std::vector<uint32_t> m_pixels;
"""

SOURCE_SNIPPET='''#include "gui/widgets/gpudump.h"
PCSX::Widgets::GPUDump::GPUDump(bool& show, std::vector<std::string>& favorites)
    : m_show(show),
      m_saveDialog([]() { return _("Save GPU dump"); }, favorites),
      m_openDialog([]() { return _("Open GPU dump"); }, favorites) {}
    if (m_openDialog.draw()) {
    ImGui::SameLine();
    ImGui::Checkbox(_("Loop"), &m_loop);
'''


class Stage455UpstreamPatchTests(unittest.TestCase):
    def test_patched_header_preserves_original_dialog_and_adds_frozen_storage(self):
        result=patched_header(HEADER_SNIPPET)
        self.assertIn("m_stepExportDialog",result)
        self.assertIn("m_frozenStepOneVRAM",result)
        self.assertIn("m_frozenStepOneFrame = 0",result)
        self.assertIn("m_openDialog",result)

    def test_patched_source_has_only_frame_one_and_detached_player_gpu(self):
        result=patched_source(SOURCE_SNIPPET)
        for marker in ("player->frame() != 1","player->gpu()->getVRAM()",
                       "m_frozenStepOneVRAM.resize", "m_stepExportDialog",
                       '"wbx"',"0x10; header[27]"):
            self.assertIn(marker,result)
        self.assertNotIn("g_emulator->m_gpu->getVRAM()",result)

    def test_snapshot_is_frozen_before_save_dialog(self):
        result=patched_source(SOURCE_SNIPPET)
        self.assertLess(result.index("m_frozenStepOneVRAM.resize"),
                        result.index("m_stepExportDialog.openDialog()"))
        self.assertIn("std::filesystem::permissions(",result)
        self.assertIn("std::remove(path.c_str())",result)
        self.assertIn("m_frozenStepOneFrame = player->frame()",result)
        self.assertIn("m_frozenStepOneVRAM, m_frozenStepOneFrame",result)
        self.assertIn("capturedFrame != 1",result)
        self.assertIn("header[16 + i] = uint8_t(capturedFrame",result)

    def test_patch_generator_rejects_changed_or_duplicate_upstream_anchors(self):
        with self.assertRaisesRegex(ValueError,"absent or duplicated"):
            patched_header(HEADER_SNIPPET.replace(
                "m_saveDialog","renamedSaveDialog"))
        with self.assertRaisesRegex(ValueError,"absent or duplicated"):
            patched_source(SOURCE_SNIPPET.replace(
                'ImGui::Checkbox(_("Loop"), &m_loop);',''))
        with self.assertRaisesRegex(ValueError,"absent or duplicated"):
            replace_once("abc abc","abc","def","test")

    def test_unified_diff_is_reproducible_and_scoped_to_gui(self):
        diff=make_diff(HEADER_SNIPPET,SOURCE_SNIPPET)
        self.assertIn("a/src/gui/widgets/gpudump.h",diff)
        self.assertIn("a/src/gui/widgets/gpudump.cc",diff)
        self.assertIn("WA1 owner-local research export",diff)
        self.assertNotIn("src/core/gpu.cc",diff)
        self.assertEqual(diff,make_diff(HEADER_SNIPPET,SOURCE_SNIPPET))


if __name__=="__main__":
    unittest.main()
