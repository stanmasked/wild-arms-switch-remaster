#pragma once

#include "field_pixels.hpp"
#include "field_save_file.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {

// Stage 295: switch-front-end-only feedback after gameplay has committed.
// The canonical field raster and both host reference captures are unchanged.
enum class StorageNotice {
  None, SdSaved, RamOnly, SdLoaded, RamLoaded,
  SdError, BadSave, NoSave, SdWarning
};
// Keep error/success mapping independent from libnx so host can test it.
[[nodiscard]] constexpr StorageNotice storage_save_notice(
    bool sd_accessible, FileSaveStatus disk_result) noexcept {
  return !sd_accessible ? StorageNotice::RamOnly :
         disk_result == FileSaveStatus::Stored ? StorageNotice::SdSaved :
                                                StorageNotice::SdError;
}
[[nodiscard]] constexpr StorageNotice storage_load_notice(
    bool restored, bool imported_from_sd, bool sd_accessible,
    FileSaveStatus disk_result, bool degraded = false) noexcept {
  if (restored)
    return imported_from_sd ?
           (degraded ? StorageNotice::SdWarning : StorageNotice::SdLoaded) :
           StorageNotice::RamLoaded;
  if (!sd_accessible || disk_result == FileSaveStatus::IoError)
    return StorageNotice::SdError;
  if (disk_result == FileSaveStatus::Corrupt)
    return StorageNotice::BadSave;
  return StorageNotice::NoSave;
}

constexpr std::uint32_t kStorageNoticeDurationMs = 900;
constexpr int kStorageNoticeX = 982;
constexpr int kStorageNoticeY = 29;
constexpr int kStorageNoticeW = 270;
constexpr int kStorageNoticeH = 51;

struct StorageFeedback {
  StorageNotice notice = StorageNotice::None;
  std::uint32_t remaining_ms = 0;
};

inline void begin_storage_notice(
    StorageFeedback& feedback, StorageNotice notice) noexcept {
  feedback.notice = notice;
  feedback.remaining_ms = notice == StorageNotice::None ?
      0 : kStorageNoticeDurationMs;
}

inline void advance_storage_notice(
    StorageFeedback& feedback, std::uint32_t elapsed_ms) noexcept {
  if (elapsed_ms >= feedback.remaining_ms) {
    feedback.remaining_ms = 0;
    feedback.notice = StorageNotice::None;
  } else {
    feedback.remaining_ms -= elapsed_ms;
  }
}

[[nodiscard]] constexpr std::uint32_t storage_notice_color(
    StorageNotice notice) noexcept {
  switch (notice) {
    case StorageNotice::SdSaved: return rgba(56, 207, 125);
    case StorageNotice::RamOnly: return rgba(244, 178, 64);
    case StorageNotice::SdLoaded: return rgba(73, 181, 225);
    case StorageNotice::RamLoaded: return rgba(104, 149, 244);
    case StorageNotice::SdError: return rgba(231, 77, 91);
    case StorageNotice::BadSave: return rgba(231, 77, 91);
    case StorageNotice::NoSave: return rgba(154, 160, 175);
    case StorageNotice::SdWarning: return rgba(244, 178, 64);
    case StorageNotice::None: break;
  }
  return rgba(0, 0, 0);
}

[[nodiscard]] constexpr const char* storage_notice_label(
    StorageNotice notice) noexcept {
  switch (notice) {
    case StorageNotice::SdSaved: return "SD SAVED";
    case StorageNotice::RamOnly: return "RAM ONLY";
    case StorageNotice::SdLoaded: return "SD LOADED";
    case StorageNotice::RamLoaded: return "RAM LOADED";
    case StorageNotice::SdError: return "SD ERROR";
    case StorageNotice::BadSave: return "BAD SAVE";
    case StorageNotice::NoSave: return "NO SAVE";
    case StorageNotice::SdWarning: return "SD WARN";
    case StorageNotice::None: break;
  }
  return "";
}

// Minimal 5x7 glyphs used for the storage status messages.
// No fonts or licensed imagery; all glyphs are authored pixel bitmaps.
[[nodiscard]] inline const std::array<std::uint8_t, 7>&
storage_notice_glyph(char c) noexcept {
  static constexpr std::array<std::uint8_t, 7> empty{0,0,0,0,0,0,0};
  static constexpr std::array<std::uint8_t, 7> a{14,17,17,31,17,17,17};
  static constexpr std::array<std::uint8_t, 7> b{30,17,17,30,17,17,30};
  static constexpr std::array<std::uint8_t, 7> d{30,17,17,17,17,17,30};
  static constexpr std::array<std::uint8_t, 7> e{31,16,16,30,16,16,31};
  static constexpr std::array<std::uint8_t, 7> l{16,16,16,16,16,16,31};
  static constexpr std::array<std::uint8_t, 7> m{17,27,21,21,17,17,17};
  static constexpr std::array<std::uint8_t, 7> n{17,25,21,19,17,17,17};
  static constexpr std::array<std::uint8_t, 7> o{14,17,17,17,17,17,14};
  static constexpr std::array<std::uint8_t, 7> r{30,17,17,30,20,18,17};
  static constexpr std::array<std::uint8_t, 7> s{15,16,16,14,1,1,30};
  static constexpr std::array<std::uint8_t, 7> v{17,17,17,17,17,10,4};
  static constexpr std::array<std::uint8_t, 7> w{17,17,17,21,21,21,10};
  static constexpr std::array<std::uint8_t, 7> y{17,17,10,4,4,4,4};
  switch (c) {
    case 'A': return a;
    case 'B': return b;
    case 'D': return d;
    case 'E': return e;
    case 'L': return l;
    case 'M': return m;
    case 'N': return n;
    case 'O': return o;
    case 'R': return r;
    case 'S': return s;
    case 'V': return v;
    case 'W': return w;
    case 'Y': return y;
    default: return empty;
  }
}

[[nodiscard]] inline bool draw_storage_notice(
    const PixelTarget& target, const StorageFeedback& feedback) noexcept {
  if (feedback.notice == StorageNotice::None ||
      feedback.remaining_ms == 0) return false;
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight ||
      target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192) return false;

  constexpr auto dark = rgba(17, 26, 40);
  constexpr auto white = rgba(245, 247, 252);
  const auto accent = storage_notice_color(feedback.notice);
  fill_raster_rect(target, kStorageNoticeX, kStorageNoticeY,
                   kStorageNoticeW, kStorageNoticeH, accent);
  fill_raster_rect(target, kStorageNoticeX + 2, kStorageNoticeY + 2,
                   kStorageNoticeW - 4, kStorageNoticeH - 4, dark);
  fill_raster_rect(target, kStorageNoticeX + 14, kStorageNoticeY + 14,
                   22, 23, accent);
  const char* label = storage_notice_label(feedback.notice);
  for (std::size_t i = 0; label[i] != '\0' && i < 16; ++i) {
    const auto& pattern = storage_notice_glyph(label[i]);
    for (int y = 0; y < 7; ++y)
      for (int x = 0; x < 5; ++x)
        if ((pattern[static_cast<std::size_t>(y)] >> (4 - x)) & 1u)
          fill_raster_rect(target, kStorageNoticeX + 52 +
                          static_cast<int>(i) * 12 + x * 2,
                          kStorageNoticeY + 17 + y * 2, 2, 2, white);
  }
  return true;
}

} // namespace wa::field
