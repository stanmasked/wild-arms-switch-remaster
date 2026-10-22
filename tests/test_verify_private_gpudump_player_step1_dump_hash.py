"""Stage456: bind patched detached Player Frame-1 VRAM to loaded native dump SHA-256."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from patch_private_pcsx_gpudump_player_step1_dump_hash import (
    PINNED, SHA256_HELPER, OLD_FILE_OPEN, NEW_FILE_OPEN, OLD_VECTOR_OPEN, NEW_VECTOR_OPEN,
    patched_core_header, patched_core_source, patched_gui_header,
    patched_gui_source, make_diff,
)
from verify_private_gpudump_player_step1_dump_hash import (
    MAGIC, HEADER, VRAM_BYTES, parse_private_dump_hash_bound_step1,
    verify_private_dump_hash_bound_step1_export,
)
from test_verify_private_pcsx_native_gpudump_import import prepared
from test_verify_private_gpudump_player_rewind_rgb import png


def container(vram,native_sha,*,frame=1,magic=MAGIC,declared=None,crc=None):
    if declared is None:
        declared=len(vram)
    if crc is None:
        crc=zlib.crc32(vram)&0xffffffff
    return HEADER.pack(magic,frame,declared,crc,native_sha)+vram


def fixture(root,*,color=0,png_rgb=None,embedded_sha=None):
    native,pre,trace=prepared(Path(root))
    vram=bytearray(pre.read_bytes())
    if color:
        vram[0:2]=color.to_bytes(2,"little")
        vram[2:4]=color.to_bytes(2,"little")
    native_sha=hashlib.sha256(native.read_bytes()).digest()
    if embedded_sha is not None:
        native_sha=embedded_sha
    snapshot_path=Path(root)/"player-step1.v2.bin"
    snapshot_path.write_bytes(container(bytes(vram),native_sha))
    image_path=Path(root)/"player-step1.png"
    if png_rgb is None:
        png_rgb=(248,0,0) if color&0x7fff==31 else (0,0,0)
    image_path.write_bytes(png(png_rgb))
    return native,pre,trace,snapshot_path,image_path


def audit(paths,**opts):
    return verify_private_dump_hash_bound_step1_export(
        *paths,x=0,y=0,width=2,height=1,**opts)


class Stage456BinaryTests(unittest.TestCase):
    def test_v2_header_is_64_bytes_and_magic_is_versioned(self):
        self.assertEqual(HEADER.size,64)
        self.assertEqual(len(MAGIC),16)
        self.assertIn(b"v2",MAGIC)

    def test_valid_frame_one_container_exposes_hash_and_payload(self):
        payload=bytes(VRAM_BYTES)
        digest=bytes(range(32))
        result=parse_private_dump_hash_bound_step1(container(payload,digest))
        self.assertEqual(result["frame"],1)
        self.assertEqual(result["native_dump_sha256"],digest.hex())
        self.assertEqual(result["raw"],payload)
        self.assertTrue(result["crc32_verified"])

    def test_v1_container_not_silently_accepted_as_v2(self):
        with self.assertRaisesRegex(ValueError,"magic/version"):
            parse_private_dump_hash_bound_step1(
                container(bytes(VRAM_BYTES),bytes(32),magic=b"WA1STEPVRAMv1\x00\x00\x00"))

    def test_wrong_frame_rejected(self):
        for frame in (0,2,5,2**64-1):
            with self.subTest(frame=frame),self.assertRaisesRegex(
                    ValueError,"not Player Frame 1"):
                parse_private_dump_hash_bound_step1(
                    container(bytes(VRAM_BYTES),bytes(32),frame=frame))

    def test_wrong_payload_length_and_crc_rejected(self):
        data=bytes(VRAM_BYTES)
        with self.assertRaisesRegex(ValueError,"declared"):
            parse_private_dump_hash_bound_step1(
                container(data,bytes(32),declared=VRAM_BYTES-2))
        with self.assertRaisesRegex(ValueError,"CRC32 mismatch"):
            parse_private_dump_hash_bound_step1(
                container(data,bytes(32),crc=1))

    def test_partial_or_trailing_binary_rejected(self):
        record=container(bytes(VRAM_BYTES),bytes(32))
        for changed in (record[:-1],record+b"x",record[:31],b""):
            with self.subTest(size=len(changed)),self.assertRaisesRegex(
                    ValueError,"exactly"):
                parse_private_dump_hash_bound_step1(changed)

    def test_snapshot_dump_digest_is_checked_against_exact_native_file(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=31)
            report=audit(p)
            expected=hashlib.sha256(p[0].read_bytes()).hexdigest()
            self.assertEqual(report["native_gpudump_sha256"],expected)
            self.assertEqual(report["snapshot_native_gpudump_sha256"],expected)
            self.assertTrue(report["snapshot_native_dump_sha256_matches"])
            self.assertTrue(report["roi_exact_rgb_equal"])
            self.assertEqual(report["status"],
                "PLAYER_STEP1_NATIVE_DUMP_HASH_BOUND_RGB_EQUALITY_BUILD_UNATTESTED")

    def test_valid_crc_but_wrong_native_dump_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,embedded_sha=hashlib.sha256(b"different dump").digest())
            with self.assertRaisesRegex(ValueError,"loaded native dump SHA-256"):
                audit(p)

    def test_expected_snapshot_png_and_native_hashes_are_independent(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            sd=hashlib.sha256(p[3].read_bytes()).hexdigest()
            pd=hashlib.sha256(p[4].read_bytes()).hexdigest()
            nd=hashlib.sha256(p[0].read_bytes()).hexdigest()
            result=audit(p,expected_snapshot_sha256=sd,
                         expected_png_sha256=pd,expected_native_sha256=nd)
            self.assertEqual(result["snapshot_file_sha256"],sd)
            for opts,err in (
                ({"expected_snapshot_sha256":"f"*64},"independent SHA-256"),
                ({"expected_png_sha256":"a"*64},"PNG differs"),
                ({"expected_native_sha256":"0"*64},"independent SHA256"),
                ({"expected_snapshot_sha256":"BAD"},"lowercase 64 hex")):
                with self.subTest(opts=opts),self.assertRaisesRegex(ValueError,err):
                    audit(p,**opts)

    def test_snapshot_and_png_mismatch_is_not_called_equal(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=31,png_rgb=(0,0,0))
            with self.assertRaisesRegex(ValueError,"PNG RGB differs"):
                audit(p)
            result=audit(p,require_exact_rgb=False)
            self.assertEqual(result["status"],
                "PLAYER_STEP1_NATIVE_DUMP_HASH_BOUND_RGB_MISMATCH_NO_VISUAL_BINDING")

    def test_bit15_only_change_is_not_visible_rgb_change(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root,color=0x8000)
            result=audit(p)
            self.assertEqual(result["change_from_native_pretrace"][
                "roi_visibly_changed_rgb555_pixel_count"],0)

    def test_static_roi_gate_is_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            with self.assertRaisesRegex(ValueError,"no visible change"):
                audit(p,require_changed_roi=True)

    def test_alias_and_symlink_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p=fixture(root)
            with self.assertRaisesRegex(ValueError,"aliased"):
                audit((*p[:3],p[1],p[4]))
            link=Path(root)/"snapshot-link"
            link.symlink_to(p[3])
            with self.assertRaisesRegex(ValueError,"aliased"):
                audit((*p[:3],link,p[4]))

    def test_report_keeps_original_payload_private(self):
        with tempfile.TemporaryDirectory() as root:
            result=audit(fixture(root,color=31))
            rendered=json.dumps(result)
            for key in ('"raw_gp0_words"','"raw_vram_u16"','"raw_png_pixels"',
                        '"disc_serial"','"original_palette_bytes"'):
                self.assertNotIn(key,rendered)
            self.assertTrue(result["interpretation"][
                "all_hashes_and_reports_remain_owner_private"])


CORE_HEADER_SNIPPET="""#include <stdint.h>
#include <memory>
#include <vector>
namespace PCSX {
class GPUDumpReader {
public:
    bool atEnd() const { return m_ptr >= m_words.size(); }
    size_t position() const { return m_ptr; }
    size_t size() const { return m_words.size(); }
private:
    std::vector<uint32_t> m_words;
    size_t m_ptr = 4;
};
class GPUDumpPlayer {
public:
    uint64_t frame() const { return m_frame; }
private:
    uint64_t m_frame = 0;
    GPUDumpReader m_reader;
};
}
"""

CORE_SOURCE_SNIPPET='#include "core/gpudump.h"\n#include <string.h>\n#include <algorithm>\n'+OLD_FILE_OPEN+"\n"+OLD_VECTOR_OPEN+"""
    if (m_words.size() < 4) return false;
    uint32_t magic[4];
    memcpy(magic, GPUDumper::c_magic, sizeof(magic));
    for (unsigned i = 0; i < 4; i++) {
        if (m_words[i] != SWAP_LE32(magic[i])) return false;
    }
    return true;
}
"""

GUI_HEADER_SNIPPET="""#include <stdint.h>
class GPUDump {
private:
    FileDialog<FileDialogMode::Save> m_saveDialog;
    FileDialog<FileDialogMode::Open> m_openDialog;
    GLuint m_texture = 0;
    std::vector<uint32_t> m_pixels;
};
"""

GUI_SOURCE_SNIPPET='''#include "gui/widgets/gpudump.h"
PCSX::Widgets::GPUDump::GPUDump(bool& show, std::vector<std::string>& favorites)
    : m_show(show),
      m_saveDialog([]() { return _("Save GPU dump"); }, favorites),
      m_openDialog([]() { return _("Open GPU dump"); }, favorites) {}
    if (m_openDialog.draw()) {
    ImGui::SameLine();
    ImGui::Checkbox(_("Loop"), &m_loop);
'''


class Stage456PatchTests(unittest.TestCase):
    def test_pinned_upstream_revision_is_exact(self):
        self.assertEqual(PINNED,"de4a33e9a69abec4f567ae33567537f867dc2bba")

    def test_core_header_exposes_loaded_dump_digest_from_reader(self):
        result=patched_core_header(CORE_HEADER_SNIPPET)
        self.assertIn("std::array<uint8_t, 32> m_sha256{}",result)
        self.assertIn("sha256() const",result)
        self.assertIn("dumpSHA256() const { return m_reader.sha256(); }",result)

    def test_reader_hashes_raw_file_before_byte_swapping(self):
        result=patched_core_source(CORE_SOURCE_SNIPPET)
        self.assertLess(result.index("m_sha256.fill(0);"),result.index("if (!file || file->failed())"))
        self.assertNotIn("exactFileDigest",result)
        self.assertIn("return open(std::move(words));",result)
        self.assertEqual(result.count("auto rawDigest = waPrivateSha256"),1)
        self.assertLess(result.index("while (total < size)"),result.index("return open(std::move(words));"))
        self.assertLess(result.index("auto rawDigest = waPrivateSha256"),result.index("m_words = std::move(words)"))
        self.assertIn("waPrivateSha256(reinterpret_cast<const uint8_t*>(words.data())",result)
        self.assertIn("size_t(got) > size - total",result)
        self.assertLess(result.index("auto rawDigest"),result.index("m_words = std::move(words)"))
        self.assertLess(result.index("if (m_words[i] != SWAP_LE32(magic[i])) {"),
                        result.index("m_sha256 = rawDigest"))
        self.assertIn("m_words.clear();",result)
        self.assertLess(result.index("m_sha256 = rawDigest"),result.index("return true;"))

    def test_reader_rejects_misaligned_or_incomplete_native_file_reads(self):
        result=patched_core_source(CORE_SOURCE_SNIPPET)
        alignment='if (size % sizeof(uint32_t) != 0) return false;'
        read_loop='while (total < size)'
        invalid_count='if (got <= 0 || size_t(got) > size - total) return false;'
        digest='auto rawDigest = waPrivateSha256'
        self.assertIn(alignment,result)
        self.assertIn(read_loop,result)
        self.assertIn(invalid_count,result)
        self.assertIn('catch (...) {',result)
        self.assertIn('size = file->size();',result)
        self.assertIn('total += size_t(got);',result)
        self.assertIn('m_words.clear();',result)
        self.assertIn('m_ptr = 4;',result)
        self.assertLess(result.index(alignment),result.index(read_loop))
        self.assertLess(result.index(invalid_count),result.index(digest))
        self.assertLess(result.index(invalid_count),result.index('return open(std::move(words));'))
        self.assertLess(result.index(digest),result.index('m_words = std::move(words)'))

    def test_reader_allocation_failure_is_caught_before_seek_or_read(self):
        result=patched_core_source(CORE_SOURCE_SNIPPET)
        allocation=(
            "std::vector<uint32_t> words;\n"
            "    try {\n"
            "        words.resize(size / sizeof(uint32_t));\n"
            "    } catch (...) {\n"
            "        return false;\n"
            "    }"
        )
        self.assertIn(allocation,result)
        self.assertLess(result.index(allocation),
                        result.index("if (file->rSeek(0, SEEK_SET) != 0) return false;"))
        self.assertLess(result.index(allocation),result.index("while (total < size)"))

    def test_reader_requires_successful_rewind_before_hashing(self):
        result=patched_core_source(CORE_SOURCE_SNIPPET)
        rewind='if (file->rSeek(0, SEEK_SET) != 0) return false;'
        read_loop='while (total < size)'
        digest='auto rawDigest = waPrivateSha256'
        self.assertIn(rewind,result)
        self.assertLess(result.index(rewind),result.index(read_loop))
        self.assertLess(result.index(read_loop),result.index(digest))

    def test_reader_rewind_exception_is_caught_before_read_or_parse(self):
        result=patched_core_source(CORE_SOURCE_SNIPPET)
        rewind='if (file->rSeek(0, SEEK_SET) != 0) return false;'
        read_loop='while (total < size)'
        digest='auto rawDigest = waPrivateSha256'
        parse='return open(std::move(words));'
        self.assertIn(rewind,result)
        rewind_pos=result.index(rewind)
        read_pos=result.index(read_loop,rewind_pos)
        catch_pos=result.index('} catch (...) {',rewind_pos)
        digest_pos=result.index(digest,rewind_pos)
        parse_pos=result.index(parse,rewind_pos)
        self.assertLess(rewind_pos,read_pos)
        self.assertLess(read_pos,catch_pos)
        self.assertLess(catch_pos,parse_pos)
        self.assertLess(parse_pos,digest_pos)
        self.assertLess(digest_pos,result.index("for (auto& w : m_words)"))

    def test_gui_embeds_loaded_dump_digest_and_v2_container(self):
        h=patched_gui_header(__import__(
            "patch_private_pcsx_gpudump_player_step1_export").patched_header(GUI_HEADER_SNIPPET))
        s=patched_gui_source(__import__(
            "patch_private_pcsx_gpudump_player_step1_export").patched_source(GUI_SOURCE_SNIPPET))
        self.assertIn("m_frozenDumpSHA256",h)
        self.assertIn("'R', 'A', 'M', 'v', '2'",s)
        self.assertIn("memcpy(header + 32, capturedDumpSHA256.data()",s)
        self.assertIn("std::string(reinterpret_cast<const char*>(selected[0].c_str()))",s)
        self.assertIn("m_frozenDumpSHA256 = player->dumpSHA256()",s)
        self.assertIn("m_frozenDumpSHA256)",s)

    def test_patch_is_scoped_to_four_pinned_upstream_files(self):
        diff=make_diff(CORE_HEADER_SNIPPET,CORE_SOURCE_SNIPPET,
                       GUI_HEADER_SNIPPET,GUI_SOURCE_SNIPPET)
        for path in ("src/core/gpudump.h","src/core/gpudump.cc",
                     "src/gui/widgets/gpudump.h","src/gui/widgets/gpudump.cc"):
            self.assertIn("a/"+path,diff)
        self.assertIn("waPrivateSha256",diff)
        self.assertIn("player->dumpSHA256()",diff)
        self.assertNotIn("src/core/gpu.cc",diff)

    def test_combined_diff_applies_to_clean_synthetic_four_file_checkout(self):
        git=shutil.which("git")
        if git is None:
            self.skipTest("git executable not installed")
        originals={
            "src/core/gpudump.h":CORE_HEADER_SNIPPET,
            "src/core/gpudump.cc":CORE_SOURCE_SNIPPET,
            "src/gui/widgets/gpudump.h":GUI_HEADER_SNIPPET,
            "src/gui/widgets/gpudump.cc":GUI_SOURCE_SNIPPET,
        }
        diff=make_diff(CORE_HEADER_SNIPPET,CORE_SOURCE_SNIPPET,
                       GUI_HEADER_SNIPPET,GUI_SOURCE_SNIPPET)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,content in originals.items():
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content)
            subprocess.run([git,"init","-q",str(root)],check=True)
            subprocess.run([git,"-C",str(root),"add","."],check=True)
            subprocess.run([git,"-C",str(root),"-c","user.name=Stage456",
                            "-c","user.email=stage456@example.invalid",
                            "commit","-qm","synthetic pristine base"],check=True)
            checked=subprocess.run([git,"-C",str(root),"apply","--check","-"],
                                   input=diff,capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
            applied=subprocess.run([git,"-C",str(root),"apply","-"],
                                   input=diff,capture_output=True,text=True)
            self.assertEqual(applied.returncode,0,applied.stderr)
            self.assertIn("m_sha256", (root/"src/core/gpudump.h").read_text())
            self.assertIn("capturedDumpSHA256.data()",
                          (root/"src/gui/widgets/gpudump.cc").read_text())

    def test_cpp_native_reader_handles_partial_reads_and_rejects_bad_io(self):
        compiler=shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("no C++ compiler installed")
        vector_tail=r'''
    m_ptr = 4;
    if (m_words.size() < 4) {
        m_words.clear();
        m_ptr = 4;
        return false;
    }
    uint32_t magic[4];
    memcpy(magic, GPUDumper::c_magic, sizeof(magic));
    for (unsigned i = 0; i < 4; i++) {
        if (m_words[i] != SWAP_LE32(magic[i])) {
            m_words.clear();
            m_ptr = 4;
            return false;
        }
    }
    m_sha256 = rawDigest;
    return true;
}
'''
        source=r'''#include <array>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <limits>
#include <string>
#include <stdexcept>
#include <utility>
#include <vector>
#include <sys/types.h>
#define SWAP_LE32(value) (value)
int vectorOpenCalls = 0;
int packetNextCalls = 0;
int gpuSetupCalls = 0;
namespace PCSX {
template<class T> using IO = std::shared_ptr<T>;
struct File {
    std::vector<uint8_t> bytes;
    size_t cursor=0;
    bool seekFails=false;
    bool seekReturnsNegative=false;
    bool sizeThrows=false;
    bool readThrows=false;
    bool overrideReportedSize=false;
    size_t reportedSize=0;
    size_t seekCalls=0;
    int mode=0;
    size_t maxChunk=static_cast<size_t>(-1);
    size_t readCalls=0;
    bool failed() const { return false; }
    size_t size() const {
        if (sizeThrows) throw std::runtime_error("size failure");
        return overrideReportedSize ? reportedSize : bytes.size();
    }
    ssize_t rSeek(ssize_t pos,int wheel) {
        ++seekCalls;
        if (seekFails) throw std::runtime_error("seek failure");
        if (seekReturnsNegative || wheel!=SEEK_SET || pos<0) return -1;
        cursor=size_t(pos);
        return ssize_t(cursor);
    }
    ssize_t read(void* dst,size_t amount) {
        ++readCalls;
        if (readThrows) throw std::runtime_error("read failure");
        if (mode==2) return ssize_t(amount+1);
        if (mode==1 && cursor>=5) return -1;
        if (cursor>=bytes.size()) return -1;
        size_t n=std::min(amount,std::min(maxChunk,bytes.size()-cursor));
        if (mode==1) n=std::min(n,size_t(5-cursor));
        std::memcpy(dst,bytes.data()+cursor,n);
        cursor+=n;
        return ssize_t(n);
    }
};
struct GPUDumper {
    static constexpr char c_magic[16] = {'P','S','X','G','P','U','D','U','M','P','v','1','r','1',0,0};
};
class GPUDumpReader {
public:
    struct Packet { uint8_t type; const uint32_t* words; uint32_t length; };
    bool open(IO<File> file);
    bool open(std::vector<uint32_t>&& words);
    const std::array<uint8_t,32>& digest() const { return m_sha256; }
    size_t position() const { return m_ptr; }
    size_t size() const { return m_words.size(); }
    void rewind() { m_ptr=4; }
    bool next(Packet& packet) {
        ++packetNextCalls;
        if (m_ptr >= m_words.size()) return false;
        uint32_t header = m_words[m_ptr++];
        packet.type = uint8_t(header >> 24);
        packet.length = header & 0xffffff;
        if (packet.length > m_words.size() - m_ptr) {
            m_ptr = m_words.size();
            return false;
        }
        packet.words = m_words.data() + m_ptr;
        m_ptr += packet.length;
        return true;
    }
private:
    std::vector<uint32_t> m_words;
    size_t m_ptr=4;
    std::array<uint8_t,32> m_sha256{};
};
struct GPU {
    static std::unique_ptr<GPU> getSoft() {
        ++gpuSetupCalls;
        return std::make_unique<GPU>();
    }
    void detach(void*) {}
    void init(void*) {}
    void shutdown() {}
    void writeStatus(uint32_t) {}
    void clearVRAM() {}
};
class GPUDumpPlayer {
public:
    bool load(IO<File> file) {
        unload();
        if (!m_reader.open(file)) return false;
        m_gpu = GPU::getSoft();
        m_gpu->detach(&m_logger);
        m_gpu->init(nullptr);
        rewind();
        return true;
    }
    void unload() {
        if (m_gpu) m_gpu->shutdown();
        m_gpu.reset();
    }
    void rewind() {
        if (!m_gpu) return;
        m_reader.rewind();
        m_gpu->writeStatus(0);
        m_gpu->clearVRAM();
        GPUDumpReader::Packet packet;
        size_t start = 4;
        while (m_reader.next(packet)) {
            if (packet.type == 5) {
                start = m_reader.position();
                break;
            }
            if (packet.type == 2) {
                m_reader.rewind();
                break;
            }
        }
        m_traceStart = start;
    }
    const std::array<uint8_t,32>& digest() const { return m_reader.digest(); }
private:
    std::unique_ptr<GPU> m_gpu;
    int m_logger = 0;
    GPUDumpReader m_reader;
    size_t m_traceStart = 4;
};
}
''' + SHA256_HELPER + "\n" + NEW_FILE_OPEN + "\n" + NEW_VECTOR_OPEN.replace("bool PCSX::GPUDumpReader::open(std::vector<uint32_t>&& words) {",
        "bool PCSX::GPUDumpReader::open(std::vector<uint32_t>&& words) {\n    ++vectorOpenCalls;") + vector_tail + r'''
int main() {
    std::vector<uint8_t> bytes={'P','S','X','G','P','U','D','U','M','P','v','1','r','1',0,0};
    auto partial=std::make_shared<PCSX::File>();
    partial->bytes=bytes;
    partial->maxChunk=3;
    PCSX::GPUDumpReader reader;
    if (!reader.open(partial)) return 1;
    if (reader.digest()!=waPrivateSha256(bytes.data(),bytes.size())) return 2;

    // The pinned PosixFile::rSeek throws on seek errors; fail closed and
    // clear the old identity and packet buffer.
    auto seekFailure=std::make_shared<PCSX::File>();
    seekFailure->bytes=bytes;
    seekFailure->seekFails=true;
    int parserCallsBeforeSeekException = vectorOpenCalls;
    int packetCallsBeforeSeekException = packetNextCalls;
    int gpuSetupBeforeSeekException = gpuSetupCalls;
    if (reader.open(seekFailure)) return 3;
    if (vectorOpenCalls != parserCallsBeforeSeekException) return 25;
    if (packetNextCalls != packetCallsBeforeSeekException) return 29;
    if (gpuSetupCalls != gpuSetupBeforeSeekException) return 30;
    if (seekFailure->readCalls != 0) return 26;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0 || reader.position()!=4) return 4;

    // Mirror the pinned Player load ordering: a valid load reaches packet
    // iteration; a subsequent throwing rewind must stop before GPU setup/rewind.
    auto playerValid=std::make_shared<PCSX::File>();
    playerValid->bytes=bytes;
    PCSX::GPUDumpPlayer player;
    int packetCallsBeforeValidPlayerLoad = packetNextCalls;
    int gpuSetupBeforeValidPlayerLoad = gpuSetupCalls;
    if (!player.load(playerValid)) return 31;
    if (gpuSetupCalls != gpuSetupBeforeValidPlayerLoad + 1) return 32;
    if (packetNextCalls <= packetCallsBeforeValidPlayerLoad) return 33;
    if (player.digest()!=waPrivateSha256(bytes.data(),bytes.size())) return 34;

    int packetCallsBeforePlayerSeekException = packetNextCalls;
    int gpuSetupBeforePlayerSeekException = gpuSetupCalls;
    if (player.load(seekFailure)) return 35;
    if (packetNextCalls != packetCallsBeforePlayerSeekException) return 36;
    if (gpuSetupCalls != gpuSetupBeforePlayerSeekException) return 37;
    if (player.digest()!=std::array<uint8_t,32>{}) return 38;

    // Also exercise backends that report seek failure as a negative value.
    auto seekNegative=std::make_shared<PCSX::File>();
    seekNegative->bytes=bytes;
    seekNegative->seekReturnsNegative=true;
    int parserCallsBeforeNegativeSeek = vectorOpenCalls;
    int packetCallsBeforeNegativeSeek = packetNextCalls;
    int gpuSetupBeforeNegativeSeek = gpuSetupCalls;
    if (reader.open(seekNegative)) return 5;
    if (vectorOpenCalls != parserCallsBeforeNegativeSeek) return 27;
    if (packetNextCalls != packetCallsBeforeNegativeSeek) return 39;
    if (gpuSetupCalls != gpuSetupBeforeNegativeSeek) return 40;
    if (seekNegative->readCalls != 0) return 28;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 6;

    int packetCallsBeforePlayerNegativeSeek = packetNextCalls;
    int gpuSetupBeforePlayerNegativeSeek = gpuSetupCalls;
    if (player.load(seekNegative)) return 41;
    if (packetNextCalls != packetCallsBeforePlayerNegativeSeek) return 42;
    if (gpuSetupCalls != gpuSetupBeforePlayerNegativeSeek) return 43;
    if (seekNegative->readCalls != 0) return 44;
    if (player.digest()!=std::array<uint8_t,32>{}) return 45;

    auto sizeFailure=std::make_shared<PCSX::File>();
    sizeFailure->bytes=bytes;
    sizeFailure->sizeThrows=true;
    if (reader.open(sizeFailure)) return 7;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 8;

    // A word-aligned but unrepresentable size must fail during buffer
    // allocation, before any seek, file read, digest, or packet parsing.
    auto allocationFailure=std::make_shared<PCSX::File>();
    allocationFailure->bytes=bytes;
    allocationFailure->overrideReportedSize=true;
    allocationFailure->reportedSize=std::numeric_limits<size_t>::max() & ~size_t(3);
    int allocationFailureParserCalls = vectorOpenCalls;
    if (reader.open(allocationFailure)) return 46;
    if (allocationFailure->seekCalls != 0 || allocationFailure->readCalls != 0) return 47;
    if (vectorOpenCalls != allocationFailureParserCalls) return 48;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0 || reader.position()!=4) return 49;

    auto readFailure=std::make_shared<PCSX::File>();
    readFailure->bytes=bytes;
    readFailure->readThrows=true;
    if (reader.open(readFailure)) return 9;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 10;

    auto interrupted=std::make_shared<PCSX::File>();
    interrupted->bytes=bytes;
    interrupted->mode=1;
    if (reader.open(interrupted)) return 11;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 12;

    auto invalidCount=std::make_shared<PCSX::File>();
    invalidCount->bytes=bytes;
    invalidCount->mode=2;
    if (reader.open(invalidCount)) return 13;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 14;

    auto misaligned=std::make_shared<PCSX::File>();
    misaligned->bytes.assign(5,1);
    if (reader.open(misaligned)) return 15;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 16;

    auto invalidHeader=std::make_shared<PCSX::File>();
    invalidHeader->bytes.assign(16,0);
    if (reader.open(invalidHeader)) return 17;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 18;

    auto shortFile=std::make_shared<PCSX::File>();
    shortFile->bytes.assign(8,0);
    if (reader.open(shortFile)) return 19;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0) return 20;

    std::vector<uint32_t> validWords(4);
    std::memcpy(validWords.data(),bytes.data(),bytes.size());
    if (!reader.open(std::move(validWords))) return 21;
    if (reader.digest()!=waPrivateSha256(bytes.data(),bytes.size())) return 22;

    std::vector<uint32_t> invalidWords(4,0);
    if (reader.open(std::move(invalidWords))) return 23;
    if (reader.digest()!=std::array<uint8_t,32>{} || reader.size()!=0 || reader.position()!=4) return 24;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"native_reader.cpp"
            exe=Path(d)/"native_reader"
            src.write_text(source)
            built=subprocess.run([compiler,"-std=c++17",str(src),"-o",str(exe)],
                                 capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,
                "native reader harness exit "+str(run.returncode)+": "+run.stderr)

    def test_cpp_sha256_matches_empty_abc_and_million_a_vectors(self):
        compiler=shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("no C++ compiler installed")
        source=r'''#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
''' + SHA256_HELPER + r'''
static void printHash(const std::array<uint8_t,32>& h) {
    for (auto b : h) std::printf("%02x", unsigned(b));
    std::printf("\n");
}
int main() {
    printHash(waPrivateSha256(nullptr,0));
    const uint8_t abc[]={'a','b','c'};
    printHash(waPrivateSha256(abc,3));
    std::vector<uint8_t> million(1000000, uint8_t('a'));
    printHash(waPrivateSha256(million.data(),million.size()));
}
'''
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"sha.cpp"
            exe=Path(d)/"sha"
            src.write_text(source)
            built=subprocess.run([compiler,"-std=c++17",str(src),"-o",str(exe)],
                                 capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            got=run.stdout.strip().splitlines()
            expected=[
                hashlib.sha256(b"").hexdigest(),
                hashlib.sha256(b"abc").hexdigest(),
                hashlib.sha256(b"a"*1000000).hexdigest(),
            ]
            self.assertEqual(got,expected)


if __name__=="__main__":
    unittest.main()
