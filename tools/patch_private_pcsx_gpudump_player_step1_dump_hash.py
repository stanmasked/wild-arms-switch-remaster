#!/usr/bin/env python3
"""Generate/apply a pinned PCSX-Redux patch binding Frame-1 VRAM to dump SHA-256.

Requires a clean checkout at upstream commit de4a33e9a69abec4f567ae33567537f867dc2bba.
--check validates without modification; --apply modifies only that owner's local checkout.
"""
import argparse
import difflib
from pathlib import Path
import subprocess

import patch_private_pcsx_gpudump_player_step1_export as stage455

PINNED=stage455.PINNED
CORE_HEADER="src/core/gpudump.h"
CORE_SOURCE="src/core/gpudump.cc"
GUI_HEADER="src/gui/widgets/gpudump.h"
GUI_SOURCE="src/gui/widgets/gpudump.cc"

SHA256_HELPER=r"""
// Small self-contained SHA-256 used to bind a Player export to the exact
// native dump bytes read by GPUDumpReader. Output bytes use SHA-256's
// standard big-endian digest representation.
static std::array<uint8_t, 32> waPrivateSha256(const uint8_t* data, size_t size) {
    static constexpr std::array<uint32_t, 64> k = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                     0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    const auto rotr = [](uint32_t v, unsigned n) { return (v >> n) | (v << (32 - n)); };
    const auto process = [&](const uint8_t* block) {
        uint32_t w[64];
        for (unsigned i = 0; i < 16; i++) {
            w[i] = (uint32_t(block[4*i]) << 24) |
                   (uint32_t(block[4*i+1]) << 16) |
                   (uint32_t(block[4*i+2]) << 8) | uint32_t(block[4*i+3]);
        }
        for (unsigned i = 16; i < 64; i++) {
            uint32_t s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
            uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        uint32_t a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], q=h[7];
        for (unsigned i = 0; i < 64; i++) {
            uint32_t s1=rotr(e,6)^rotr(e,11)^rotr(e,25);
            uint32_t ch=(e&f)^((~e)&g);
            uint32_t t1=q+s1+ch+k[i]+w[i];
            uint32_t s0=rotr(a,2)^rotr(a,13)^rotr(a,22);
            uint32_t maj=(a&b)^(a&c)^(b&c);
            uint32_t t2=s0+maj;
            q=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d;
        h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=q;
    };
    size_t offset = 0;
    while (size - offset >= 64) {
        process(data + offset);
        offset += 64;
    }
    std::array<uint8_t, 128> tail{};
    size_t remaining = size - offset;
    if (remaining) memcpy(tail.data(), data + offset, remaining);
    tail[remaining] = 0x80;
    const size_t tailSize = remaining < 56 ? 64 : 128;
    const uint64_t bitLength = uint64_t(size) * 8;
    for (unsigned i = 0; i < 8; i++) tail[tailSize - 1 - i] = uint8_t(bitLength >> (8 * i));
    process(tail.data());
    if (tailSize == 128) process(tail.data() + 64);
    std::array<uint8_t, 32> result{};
    for (unsigned i = 0; i < 8; i++) {
        result[4*i] = uint8_t(h[i] >> 24);
        result[4*i+1] = uint8_t(h[i] >> 16);
        result[4*i+2] = uint8_t(h[i] >> 8);
        result[4*i+3] = uint8_t(h[i]);
    }
    return result;
}
"""


def replace_once(text, needle, replacement, part):
    if text.count(needle) != 1:
        raise ValueError("pinned upstream " + part + " anchor absent or duplicated")
    return text.replace(needle, replacement, 1)


OLD_FILE_OPEN = """bool PCSX::GPUDumpReader::open(IO<File> file) {
    if (!file || file->failed()) return false;
    size_t size = file->size();
    std::vector<uint32_t> words(size / 4);
    file->rSeek(0, SEEK_SET);
    ssize_t got = file->read(words.data(), words.size() * 4);
    // Keep only what was actually read; next() then stops at a packet cut short.
    words.resize(got > 0 ? size_t(got) / 4 : 0);
    return open(std::move(words));
}"""

NEW_FILE_OPEN = """bool PCSX::GPUDumpReader::open(IO<File> file) {
    // A failed reopen must never leave a prior file's identity available.
    m_sha256.fill(0);
    m_words.clear();
    m_ptr = 4;
    if (!file || file->failed()) return false;
    size_t size = 0;
    // PCSX-Redux File implementations may throw when size/seek/read fails.
    // Convert those I/O failures to a closed reader instead of leaking them
    // through the Player UI or continuing with an unverified stream.
    try {
        size = file->size();
    } catch (...) {
        return false;
    }
    // Native GPUDUMP packets are 32-bit words; reject malformed tails rather
    // than hashing bytes the packet reader would silently discard.
    if (size % sizeof(uint32_t) != 0) return false;
    std::vector<uint32_t> words(size / sizeof(uint32_t));
    size_t total = 0;
    try {
        // In the pinned PCSX-Redux source, PosixFile::rSeek throws
        // std::runtime_error when fseek fails (and base File::rSeek throws
        // by default). Alternate backends may return a negative sentinel.
        // A zero return means the cursor is now at byte zero.
        if (file->rSeek(0, SEEK_SET) != 0) return false;
        while (total < size) {
            ssize_t got = file->read(reinterpret_cast<uint8_t*>(words.data()) + total, size - total);
            if (got <= 0 || size_t(got) > size - total) return false;
            total += size_t(got);
        }
    } catch (...) {
        return false;
    }
    auto exactFileDigest = waPrivateSha256(reinterpret_cast<const uint8_t*>(words.data()), size);
    bool valid = open(std::move(words));
    if (valid) m_sha256 = exactFileDigest;
    return valid;
}"""

OLD_VECTOR_OPEN = """bool PCSX::GPUDumpReader::open(std::vector<uint32_t>&& words) {
    m_words = std::move(words);
    for (auto& w : m_words) w = SWAP_LE32(w);"""

NEW_VECTOR_OPEN = """bool PCSX::GPUDumpReader::open(std::vector<uint32_t>&& words) {
    // Hash the original byte representation before word swapping, but publish
    // it only if the complete native GPUDUMP header is valid.
    m_sha256.fill(0);
    auto rawDigest = waPrivateSha256(reinterpret_cast<const uint8_t*>(words.data()),
                                     words.size() * sizeof(uint32_t));
    m_words = std::move(words);
    for (auto& w : m_words) w = SWAP_LE32(w);"""


def patched_core_header(source):
    source = replace_once(source, "#include <stdint.h>\n",
        "#include <stdint.h>\n\n#include <array>\n", "core header array include")
    source = replace_once(source,
        "    bool atEnd() const { return m_ptr >= m_words.size(); }\n    size_t position() const { return m_ptr; }\n    size_t size() const { return m_words.size(); }\n",
        "    bool atEnd() const { return m_ptr >= m_words.size(); }\n"
        "    size_t position() const { return m_ptr; }\n"
        "    size_t size() const { return m_words.size(); }\n"
        "    const std::array<uint8_t, 32>& sha256() const { return m_sha256; }\n",
        "reader public SHA-256 accessor")
    source = replace_once(source, "    std::vector<uint32_t> m_words;\n    size_t m_ptr = 4;\n",
        "    std::vector<uint32_t> m_words;\n"
        "    std::array<uint8_t, 32> m_sha256{};\n"
        "    size_t m_ptr = 4;\n", "reader digest storage")
    source = replace_once(source, "    uint64_t frame() const { return m_frame; }\n",
        "    uint64_t frame() const { return m_frame; }\n"
        "    const std::array<uint8_t, 32>& dumpSHA256() const { return m_reader.sha256(); }\n",
        "player loaded-dump SHA-256 accessor")
    return source


def patched_core_source(source):
    source = replace_once(source, OLD_FILE_OPEN, SHA256_HELPER + "\n\n" + NEW_FILE_OPEN,
                          "native file open and SHA-256 helper")
    source = replace_once(source, OLD_VECTOR_OPEN, NEW_VECTOR_OPEN,
                          "in-memory reader digest")
    source = replace_once(source,
        "    for (unsigned i = 0; i < 4; i++) {\n"
        "        if (m_words[i] != SWAP_LE32(magic[i])) return false;\n"
        "    }\n"
        "    return true;\n}",
        "    if (m_words.size() < 4) {\n"
        "        m_words.clear();\n"
        "        m_ptr = 4;\n"
        "        return false;\n"
        "    }\n"
        "    for (unsigned i = 0; i < 4; i++) {\n"
        "        if (m_words[i] != SWAP_LE32(magic[i])) {\n"
        "            m_words.clear();\n"
        "            m_ptr = 4;\n"
        "            return false;\n"
        "        }\n"
        "    }\n"
        "    m_sha256 = rawDigest;\n"
        "    return true;\n}",
        "commit reader digest only after valid native header")
    return source


def patched_gui_header(source):
    source = replace_once(source, "#include <stdint.h>\n",
        "#include <stdint.h>\n\n#include <array>\n", "GUI array include")
    source = replace_once(source, "    uint64_t m_frozenStepOneFrame = 0;\n",
        "    uint64_t m_frozenStepOneFrame = 0;\n"
        "    std::array<uint8_t, 32> m_frozenDumpSHA256{};\n",
        "GUI frozen dump digest")
    return source


def patched_gui_source(source):
    source = replace_once(source, "#include <cstdio>\n",
        "#include <cstdio>\n#include <cstring>\n", "GUI memcpy include")
    source = replace_once(source,
        "static bool wa1WriteFrozenStepOneVRAM(const std::string& path, const std::vector<uint8_t>& pixels, uint64_t capturedFrame) {",
        "static bool wa1WriteFrozenStepOneVRAM(const std::string& path, const std::vector<uint8_t>& pixels, "
        "uint64_t capturedFrame, const std::array<uint8_t, 32>& capturedDumpSHA256) {",
        "version 2 writer signature")
    source = replace_once(source,
        "    uint8_t header[32] = {'W', 'A', '1', 'S', 'T', 'E', 'P', 'V',\n"
        "                          'R', 'A', 'M', 'v', '1', 0, 0, 0};",
        "    uint8_t header[64] = {'W', 'A', '1', 'S', 'T', 'E', 'P', 'V',\n"
        "                          'R', 'A', 'M', 'v', '2', 0, 0, 0};",
        "version 2 snapshot header")
    source = replace_once(source,
        "    for (unsigned i = 0; i < 4; i++) header[28 + i] = uint8_t(crc >> (8 * i));\n",
        "    for (unsigned i = 0; i < 4; i++) header[28 + i] = uint8_t(crc >> (8 * i));\n"
        "    memcpy(header + 32, capturedDumpSHA256.data(), capturedDumpSHA256.size());\n",
        "native dump digest in binary header")
    source = replace_once(source,
        "wa1WriteFrozenStepOneVRAM(std::string(reinterpret_cast<const char*>(selected[0].c_str())), "
        "m_frozenStepOneVRAM, m_frozenStepOneFrame)",
        "wa1WriteFrozenStepOneVRAM(std::string(reinterpret_cast<const char*>(selected[0].c_str())), "
        "m_frozenStepOneVRAM, m_frozenStepOneFrame, m_frozenDumpSHA256)",
        "save frozen dump digest")
    source = replace_once(source, "        m_frozenStepOneFrame = 0;\n",
        "        m_frozenStepOneFrame = 0;\n"
        "        m_frozenDumpSHA256.fill(0);\n", "clear frozen dump digest")
    source = replace_once(source, "            m_frozenStepOneFrame = player->frame();\n",
        "            m_frozenStepOneFrame = player->frame();\n"
        "            m_frozenDumpSHA256 = player->dumpSHA256();\n",
        "freeze loaded native dump identity")
    return source


def unified(old, new, path):
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="a/" + path, tofile="b/" + path))


def make_diff(core_header, core_source, gui_header, gui_source):
    # Stage455 changes are generated in memory first, so the complete patch
    # remains applicable to the exact pristine pinned upstream revision.
    new_core_header = patched_core_header(core_header)
    new_core_source = patched_core_source(core_source)
    new_gui_header = patched_gui_header(stage455.patched_header(gui_header))
    new_gui_source = patched_gui_source(stage455.patched_source(gui_source))
    return "".join((
        unified(core_header, new_core_header, CORE_HEADER),
        unified(core_source, new_core_source, CORE_SOURCE),
        unified(gui_header, new_gui_header, GUI_HEADER),
        unified(gui_source, new_gui_source, GUI_SOURCE),
    ))


def check_or_apply(repository, apply=False):
    repository = Path(repository)
    if not repository.is_dir():
        raise ValueError("PCSX-Redux directory not found")
    pinned = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()
    if pinned != PINNED:
        raise ValueError("refusing unpinned PCSX-Redux checkout: " + pinned)
    clean = subprocess.run(["git", "-C", str(repository), "status", "--porcelain"],
        check=True, capture_output=True, text=True).stdout
    if clean:
        raise ValueError("PCSX-Redux checkout must be clean before applying")
    files = {p: (repository / p).read_text(encoding="utf-8")
             for p in (CORE_HEADER, CORE_SOURCE, GUI_HEADER, GUI_SOURCE)}
    patch = make_diff(files[CORE_HEADER], files[CORE_SOURCE],
                      files[GUI_HEADER], files[GUI_SOURCE])
    if not patch:
        raise ValueError("empty PCSX-Redux dump-hash binding patch")
    check = subprocess.run(["git", "-C", str(repository), "apply", "--check", "-"],
        input=patch, capture_output=True, text=True)
    if check.returncode:
        raise ValueError("generated native dump hash patch rejected: " + check.stderr[:700])
    if apply:
        subprocess.run(["git", "-C", str(repository), "apply", "-"],
            input=patch, check=True, capture_output=True, text=True)
    return patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_redux_checkout")
    parser.add_argument("--apply", action="store_true",
        help="Modify the owner's clean pinned checkout")
    args = parser.parse_args()
    patch = check_or_apply(args.pinned_pcsx_redux_checkout, args.apply)
    print(("Applied" if args.apply else "Validated") +
          " pinned Player native dump SHA-256 binding patch; diff size " +
          str(len(patch.encode("utf-8"))) + " bytes.")


if __name__ == "__main__":
    main()
