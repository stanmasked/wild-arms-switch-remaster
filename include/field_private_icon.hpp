#pragma once

// Optional, PRIVATE, owner-supplied 256x256 indexed PS1 icon preview.
// Do not bundle original game artwork in the public source or NRO.
// WAIC v1 is a remaster-private interchange format, not an original PS1 format.
#include "field_pixels.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace wa::field {

constexpr int kPrivateIconSide = 256;
constexpr std::size_t kPrivateIconPixels = 256u * 256u;
constexpr std::size_t kPrivateIconPaletteBytes = 16u * 4u;
constexpr std::size_t kPrivateIconHeaderBytes = 24u;
constexpr std::size_t kPrivateIconFileBytes =
    kPrivateIconHeaderBytes + kPrivateIconPaletteBytes + kPrivateIconPixels;

struct PrivateIcon {
  std::array<std::uint32_t, 16> palette{};
  std::array<std::uint8_t, kPrivateIconPixels> indices{};
  bool valid = false;
};

[[nodiscard]] inline std::uint16_t private_icon_u16(
    const std::uint8_t* p) noexcept {
  return static_cast<std::uint16_t>(p[0]) |
         (static_cast<std::uint16_t>(p[1]) << 8);
}

[[nodiscard]] inline std::uint32_t private_icon_u32(
    const std::uint8_t* p) noexcept {
  return static_cast<std::uint32_t>(p[0]) |
         (static_cast<std::uint32_t>(p[1]) << 8) |
         (static_cast<std::uint32_t>(p[2]) << 16) |
         (static_cast<std::uint32_t>(p[3]) << 24);
}

// Standard CRC-32/ISO-HDLC over palette + index bytes, not a signature of
// original asset provenance. Reject corrupt/truncated local media input.
[[nodiscard]] inline std::uint32_t private_icon_crc32(
    const std::uint8_t* bytes, std::size_t size) noexcept {
  std::uint32_t crc = 0xFFFFFFFFu;
  for (std::size_t i = 0; i < size; ++i) {
    crc ^= bytes[i];
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1u) ? 0xEDB88320u : 0u);
  }
  return ~crc;
}

[[nodiscard]] inline bool decode_private_icon(
    const std::uint8_t* bytes, const std::size_t size,
    PrivateIcon& out) noexcept {
  // Ensure stale content is never displayed after a failed read.
  out.valid = false;
  if (!bytes || size != kPrivateIconFileBytes) return false;
  if (bytes[0] != 'W' || bytes[1] != 'A' ||
      bytes[2] != 'I' || bytes[3] != 'C') return false;
  if (private_icon_u32(bytes + 4) != 1u ||
      private_icon_u16(bytes + 8) != kPrivateIconSide ||
      private_icon_u16(bytes + 10) != kPrivateIconSide ||
      private_icon_u16(bytes + 12) != 16u ||
      private_icon_u16(bytes + 14) != 0u ||
      private_icon_u32(bytes + 16) !=
          kPrivateIconPaletteBytes + kPrivateIconPixels)
    return false;
  if (private_icon_crc32(bytes + kPrivateIconHeaderBytes,
                         kPrivateIconPaletteBytes + kPrivateIconPixels) !=
      private_icon_u32(bytes + 20))
    return false;

  const std::uint8_t* const palette_data = bytes + kPrivateIconHeaderBytes;
  const std::uint8_t* const pixels = palette_data + kPrivateIconPaletteBytes;
  for (int i = 0; i < 16; ++i) {
    // v1 is explicitly an opaque *inspection preview*. Original PS1 STP
    // and transparency handling are not silently assigned.
    if (palette_data[4 * i + 3] != 255u) return false;
  }
  for (std::size_t i = 0; i < kPrivateIconPixels; ++i)
    if (pixels[i] >= 16) return false;

  for (int i = 0; i < 16; ++i)
    out.palette[static_cast<std::size_t>(i)] =
        private_icon_u32(palette_data + 4 * i);
  for (std::size_t i = 0; i < kPrivateIconPixels; ++i)
    out.indices[i] = pixels[i];
  out.valid = true;
  return true;
}

// Load once at start, only in a build explicitly opting into PRIVATE preview.
// Never touches saves, game progress or other game input states.
[[nodiscard]] inline bool load_private_icon_file(
    const char* path, PrivateIcon& out) noexcept {
  out.valid = false;
  if (!path) return false;
  std::FILE* source = std::fopen(path, "rb");
  if (!source) return false;
  std::array<std::uint8_t, kPrivateIconFileBytes> bytes{};
  const bool complete = std::fread(bytes.data(), 1, bytes.size(), source) ==
      bytes.size();
  const int trailing = std::fgetc(source);
  const int closed = std::fclose(source);
  if (!complete || trailing != EOF || closed != 0) return false;
  return decode_private_icon(bytes.data(), bytes.size(), out);
}

// Reject incomplete/undersized targets instead of clipping outside the
// documented inspection viewport. A failed draw makes ZERO pixel changes.
[[nodiscard]] inline bool draw_private_icon(
    const PrivateIcon& icon, const PixelTarget& target,
    int left, int top) noexcept {
  if (!icon.valid || !target.pixels || target.width <= 0 ||
      target.height <= 0 || target.stride_pixels < target.width ||
      target.stride_pixels > 8192 || left < 0 || top < 0 ||
      left > target.width - kPrivateIconSide ||
      top > target.height - kPrivateIconSide)
    return false;
  for (int y = 0; y < kPrivateIconSide; ++y) {
    auto* line = target.pixels +
        static_cast<std::size_t>(top + y) *
        static_cast<std::size_t>(target.stride_pixels) +
        static_cast<std::size_t>(left);
    for (int x = 0; x < kPrivateIconSide; ++x) {
      const auto idx = icon.indices[static_cast<std::size_t>(y) *
          kPrivateIconSide + static_cast<std::size_t>(x)];
      if (idx >= 16) return false; // normally guaranteed by decoder
      line[x] = icon.palette[idx];
    }
  }
  return true;
}

} // namespace wa::field
