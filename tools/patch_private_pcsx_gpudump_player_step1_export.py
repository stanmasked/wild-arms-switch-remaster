#!/usr/bin/env python3
"""Generate/apply a PINNED owner-local PCSX-Redux GPU Dump Player patch.

Creates an opt-in GUI export of the detached SOFTWARE GPU VRAM at
Player Frame == 1, preserving the VRAM snapshot at button-click time
until Save. No original game files are included in this repository.

Requires a clean PCSX-Redux checkout at the exact upstream commit.
--check produces a diff without modifying upstream. --apply explicitly
modifies that owner's local emulator checkout; never public CI.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

PINNED="de4a33e9a69abec4f567ae33567537f867dc2bba"
HEADER="src/gui/widgets/gpudump.h"
SOURCE="src/gui/widgets/gpudump.cc"


def replace_once(text,needle,replacement,part):
    if text.count(needle)!=1:
        raise ValueError("pinned upstream "+part+" anchor absent or duplicated")
    return text.replace(needle,replacement,1)


EXPORT_HELPER=r"""
// WA1 owner-local research export; format specified in Stage455.
// The 'x' modifier is C11 exclusive-create. Never silently replace
// an existing original-frame witness or user file.
static bool wa1WriteFrozenStepOneVRAM(const std::string& path, const std::vector<uint8_t>& pixels, uint64_t capturedFrame) {
    if (pixels.size() != 1024u * 512u * 2u || capturedFrame != 1) return false;
    FILE* handle = std::fopen(path.c_str(), "wbx");
    if (!handle) return false;
    // Set owner-only permissions before writing any content.
    std::error_code permissionError;
    std::filesystem::permissions(
        path,
        std::filesystem::perms::owner_read | std::filesystem::perms::owner_write,
        std::filesystem::perm_options::replace, permissionError);
    if (permissionError) {
        std::fclose(handle);
        std::remove(path.c_str());
        return false;
    }
    uint8_t header[32] = {'W', 'A', '1', 'S', 'T', 'E', 'P', 'V',
                          'R', 'A', 'M', 'v', '1', 0, 0, 0};
    // Versioned fixed-size record: 16-byte magic, frame u64 LE == 1,
    // VRAM byte length u32 LE, CRC32 of the following raw VRAM u32 LE.
    for (unsigned i = 0; i < 8; i++) header[16 + i] = uint8_t(capturedFrame >> (8 * i));
    header[24] = 0x00; header[25] = 0x00;
    header[26] = 0x10; header[27] = 0x00; // 1 MiB
    uint32_t crc = uint32_t(crc32(0L, Z_NULL, 0));
    crc = uint32_t(crc32(crc, pixels.data(), uInt(pixels.size())));
    for (unsigned i = 0; i < 4; i++) header[28 + i] = uint8_t(crc >> (8 * i));
    bool ok = std::fwrite(header, 1, sizeof(header), handle) == sizeof(header);
    if (ok) ok = std::fwrite(pixels.data(), 1, pixels.size(), handle) == pixels.size();
    if (std::fflush(handle)) ok = false;
    if (std::fclose(handle)) ok = false;
    if (!ok) std::remove(path.c_str());
    return ok;
}
"""


def patched_header(source):
    source=replace_once(source,
        "    FileDialog<FileDialogMode::Save> m_saveDialog;\n",
        "    FileDialog<FileDialogMode::Save> m_saveDialog;\n"
        "    FileDialog<FileDialogMode::Save> m_stepExportDialog;\n",
        "header save dialog")
    source=replace_once(source,
        "    std::vector<uint32_t> m_pixels;\n",
        "    std::vector<uint32_t> m_pixels;\n"
        "    std::vector<uint8_t> m_frozenStepOneVRAM;\n"
        "    uint64_t m_frozenStepOneFrame = 0;\n",
        "header GPU frozen snapshot storage")
    return source


def patched_source(source):
    source=replace_once(source,
        '#include "gui/widgets/gpudump.h"\n',
        '#include "gui/widgets/gpudump.h"\n\n'
        '#include <cstdio>\n#include <filesystem>\n#include <system_error>\n'
        '#include <zlib.h>\n',
        "C++ includes")
    source=replace_once(source,
        "      m_saveDialog([]() { return _(\"Save GPU dump\"); }, favorites),\n",
        "      m_saveDialog([]() { return _(\"Save GPU dump\"); }, favorites),\n"
        '      m_stepExportDialog([]() { return _("Save first-Step private VRAM"); }, favorites),\n',
        "GUI constructor")
    source=replace_once(source,
        'PCSX::Widgets::GPUDump::GPUDump(bool& show, std::vector<std::string>& favorites)\n',
        EXPORT_HELPER+"\n"
        'PCSX::Widgets::GPUDump::GPUDump(bool& show, std::vector<std::string>& favorites)\n',
        "private snapshot writer function")
    source=replace_once(source,
        '    if (m_openDialog.draw()) {\n',
        '    if (m_stepExportDialog.draw()) {\n'
        '        auto& selected = m_stepExportDialog.selected();\n'
        '        if (!selected.empty()) {\n'
        '            if (!wa1WriteFrozenStepOneVRAM(std::string(reinterpret_cast<const char*>(selected[0].c_str())), m_frozenStepOneVRAM, m_frozenStepOneFrame)) {\n'
        '                m_error = _("Unable to export private GPU Player Step 1 VRAM (or file already exists).");\n'
        '            } else {\n'
        '                m_error.clear();\n'
        '            }\n'
        '        }\n'
        '        m_frozenStepOneVRAM.clear();\n'
        '        m_frozenStepOneFrame = 0;\n'
        '    }\n'
        '    if (m_openDialog.draw()) {\n',
        "Step Save dialog")
    source=replace_once(source,
        '    ImGui::SameLine();\n    ImGui::Checkbox(_("Loop"), &m_loop);\n',
        '    ImGui::SameLine();\n'
        '    ImGui::BeginDisabled(m_playing || player->frame() != 1);\n'
        '    if (ImGui::Button(_("Export Step 1 private VRAM..."))) {\n'
        '        // Snapshot is copied NOW, not after a filename dialog; it\n'
        '        // always corresponds to the frame label visible at click.\n'
        '        Slice state = player->gpu()->getVRAM();\n'
        '        if (state.size() != 1024u * 512u * 2u) {\n'
        '            m_error = _("Detached player VRAM is not exactly 1 MiB.");\n'
        '        } else {\n'
        '            m_frozenStepOneFrame = player->frame();\n'
        '            m_frozenStepOneVRAM.resize(1024u * 512u * 2u);\n'
        '            const uint16_t* words = state.data<uint16_t>();\n'
        '            for (unsigned i = 0; i < 1024u * 512u; i++) {\n'
        '                m_frozenStepOneVRAM[2 * i] = uint8_t(words[i]);\n'
        '                m_frozenStepOneVRAM[2 * i + 1] = uint8_t(words[i] >> 8);\n'
        '            }\n'
        '            m_stepExportDialog.openDialog();\n'
        '        }\n'
        '    }\n'
        '    ImGui::EndDisabled();\n'
        '    ImGui::SameLine();\n'
        '    ImGui::Checkbox(_("Loop"), &m_loop);\n',
        "Player Step 1 capture button")
    return source


def make_diff(header,source):
    modified_header=patched_header(header)
    modified_source=patched_source(source)
    return "".join([
        "".join(difflib.unified_diff(
            header.splitlines(keepends=True),
            modified_header.splitlines(keepends=True),
            fromfile="a/"+HEADER,tofile="b/"+HEADER)),
        "".join(difflib.unified_diff(
            source.splitlines(keepends=True),
            modified_source.splitlines(keepends=True),
            fromfile="a/"+SOURCE,tofile="b/"+SOURCE))
    ])


def check_or_apply(repository,apply=False):
    repository=Path(repository)
    if not repository.is_dir():
        raise ValueError("PCSX-Redux directory not found")
    pinned=subprocess.run(
        ["git","-C",str(repository),"rev-parse","HEAD"],
        check=True,capture_output=True,text=True).stdout.strip()
    if pinned!=PINNED:
        raise ValueError("refusing unpinned PCSX-Redux checkout: "+pinned)
    clean=subprocess.run(
        ["git","-C",str(repository),"status","--porcelain"],
        check=True,capture_output=True,text=True).stdout
    if clean:
        raise ValueError("PCSX-Redux checkout must be clean before applying")
    header=(repository/HEADER).read_text(encoding="utf-8")
    source=(repository/SOURCE).read_text(encoding="utf-8")
    patch=make_diff(header,source)
    if not patch:
        raise ValueError("empty GPUDump Player patch")
    check=subprocess.run(
        ["git","-C",str(repository),"apply","--check","-"],
        input=patch,capture_output=True,text=True)
    if check.returncode:
        raise ValueError("generated GPUDump Player patch rejected: "+check.stderr[:500])
    if apply:
        subprocess.run(["git","-C",str(repository),"apply","-"],
                       input=patch,check=True,capture_output=True,text=True)
    return patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply",action="store_true",
                        help="Modify the owner's clean pinned checkout")
    args=parser.parse_args()
    patch=check_or_apply(args.pinned_pcsx_redux_checkout,args.apply)
    print(("Applied" if args.apply else "Validated")+
          " PCSX-Redux Step1 export patch; diff size "+
          str(len(patch.encode("utf-8")))+" bytes.")


if __name__=="__main__":
    main()
