#pragma once

#include "field_pixels.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {

// Stage 306: original asset-free contextual inspection caption. The
// gameplay and serialized state are untouched; only the manual field
// renderer calls this after a successful A-facing inspection.
// Place interaction text in the unobscured upper-right of the 1280x720
// game viewport. NeXium's non-game performance HUD covers top-left,
// previously hiding the inspection caption from the player and auditors.
constexpr int kInspectionPanelX = 1000;
constexpr int kInspectionPanelY = 34;
constexpr int kInspectionPanelWidth = 238;
constexpr int kInspectionPanelHeight = 55;

[[nodiscard]] constexpr const char* inspection_caption(
    Trigger marker, bool logged = false) noexcept {
  if (marker == Trigger::Event && logged) return "CLUE NOTED";
  return marker == Trigger::Event ? "EVENT AHEAD" :
         marker == Trigger::Exit ? "EXIT AHEAD" : "";
}

// Exactly the eight glyphs used by these captions, plus the blank space.
// Each glyph is a 5-bit-wide, 7-row original raster.
[[nodiscard]] inline const std::array<std::uint8_t, 7>&
inspection_caption_glyph(char c) noexcept {
  static constexpr std::array<std::uint8_t, 7> empty{0,0,0,0,0,0,0};
  static constexpr std::array<std::uint8_t, 7> a{14,17,17,31,17,17,17};
  static constexpr std::array<std::uint8_t, 7> glyph_c{14,17,16,16,16,17,14};
  static constexpr std::array<std::uint8_t, 7> l{16,16,16,16,16,16,31};
  static constexpr std::array<std::uint8_t, 7> o{14,17,17,17,17,17,14};
  static constexpr std::array<std::uint8_t, 7> u{17,17,17,17,17,17,14};
  static constexpr std::array<std::uint8_t, 7> d{30,17,17,17,17,17,30};
  static constexpr std::array<std::uint8_t, 7> e{31,16,16,30,16,16,31};
  static constexpr std::array<std::uint8_t, 7> h{17,17,17,31,17,17,17};
  static constexpr std::array<std::uint8_t, 7> i{14,4,4,4,4,4,14};
  static constexpr std::array<std::uint8_t, 7> n{17,25,21,19,17,17,17};
  static constexpr std::array<std::uint8_t, 7> t{31,4,4,4,4,4,4};
  static constexpr std::array<std::uint8_t, 7> v{17,17,17,17,17,10,4};
  static constexpr std::array<std::uint8_t, 7> x{17,17,10,4,10,17,17};
  switch (c) {
    case 'A': return a;
    case 'C': return glyph_c;
    case 'L': return l;
    case 'O': return o;
    case 'U': return u;
    case 'D': return d;
    case 'E': return e;
    case 'H': return h;
    case 'I': return i;
    case 'N': return n;
    case 'T': return t;
    case 'V': return v;
    case 'X': return x;
    default: return empty;
  }
}

[[nodiscard]] inline bool draw_inspection_caption(
    const PixelTarget& target, Trigger marker,
    bool logged = false) noexcept {
  if (marker != Trigger::Event && marker != Trigger::Exit) return false;
  if (target.pixels == nullptr ||
      target.width != kRasterWidth || target.height != kRasterHeight ||
      target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192) return false;
  const std::uint32_t accent =
      marker == Trigger::Event && logged ? rgba(105, 160, 230) :
      marker == Trigger::Event ? rgba(255, 247, 172) :
                                 rgba(172, 255, 230);
  fill_raster_rect(target, kInspectionPanelX, kInspectionPanelY,
                   kInspectionPanelWidth, kInspectionPanelHeight, accent);
  fill_raster_rect(target, kInspectionPanelX + 3, kInspectionPanelY + 3,
                   kInspectionPanelWidth - 6, kInspectionPanelHeight - 6,
                   rgba(17, 26, 40));
  const char* label = inspection_caption(marker, logged);
  for (std::size_t i = 0; label[i] != '\0' && i < 16; ++i) {
    const auto& glyph = inspection_caption_glyph(label[i]);
    for (int y = 0; y < 7; ++y)
      for (int x = 0; x < 5; ++x)
        if ((glyph[static_cast<std::size_t>(y)] >> (4-x)) & 1u)
          fill_raster_rect(target, kInspectionPanelX + 20 +
                           static_cast<int>(i)*15 + x*2,
                           kInspectionPanelY + 20 + y*2, 2, 2,
                           rgba(246, 247, 252));
  }
  return true;
}

} // namespace wa::field
