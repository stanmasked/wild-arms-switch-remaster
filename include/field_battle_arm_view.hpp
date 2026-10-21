#pragma once
// Stage398: experimental opt-in ARM ammunition and controls overlay.
// Compiled into native Switch only when WA_ARM_EXPERIMENTAL=1;
// the standard R battle and normal Switch NRO remain unchanged.
#include "field_battle_arm.hpp"
#include "field_battle_view.hpp"

#include <cstdint>
#include <cstdio>

namespace wa::field {

enum class ArmHudStatus : std::uint8_t {
  Rendered, InvalidTarget, InvalidBattle, InvalidMagazine
};

constexpr int kArmHudX = 944;
constexpr int kArmHudY = 622;
constexpr int kArmHudWidth = 286;
constexpr int kArmHudHeight = 84;

// The caller explicitly opts in AFTER an already rendered battle frame.
// On invalid target, battle, or magazine state, writes exactly ZERO pixels.
[[nodiscard]] inline ArmHudStatus draw_battle_arm_status(
    const PixelTarget& target, const FieldBattle& battle,
    const ArmMagazine& magazine) noexcept {
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight ||
      target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192)
    return ArmHudStatus::InvalidTarget;
  if (!valid_field_battle(battle)) return ArmHudStatus::InvalidBattle;
  if (!valid_arm_magazine(magazine)) return ArmHudStatus::InvalidMagazine;

  fill_raster_rect(target,kArmHudX,kArmHudY,
                   kArmHudWidth,kArmHudHeight,kBattlePanel);
  battle_outline(target,kArmHudX,kArmHudY,
                 kArmHudWidth,kArmHudHeight,kBattleGold);
  char label[32]{};
  (void)std::snprintf(label,sizeof(label),"ARM AMMO %u/%u",
                      static_cast<unsigned>(magazine.rounds),
                      static_cast<unsigned>(magazine.capacity));
  battle_text(target,kArmHudX+20,kArmHudY+14,label,kBattleWhite);
  // 8 glyphs start just to the right of the longest ARM AMMO label;
  // optional ZR attack is visible without modifying the 20-char hint.
  constexpr char kBurstHint[]="ZR BURST";
  static_assert(sizeof(kBurstHint)-1==8);
  static_assert(174+7*13+10<kArmHudWidth-4);
  battle_text(target,kArmHudX+174,kArmHudY+14,kBurstHint,kBattleGold);

  // 220 * 255 fits uint32; capacity was checked positive.
  constexpr std::uint32_t width=220;
  const std::uint32_t filled =
      (static_cast<std::uint32_t>(magazine.rounds)*width) /
      static_cast<std::uint32_t>(magazine.capacity);
  fill_raster_rect(target,kArmHudX+20,kArmHudY+38,
                   static_cast<int>(width),8,kBattleBackground);
  if(filled)
    fill_raster_rect(target,kArmHudX+20,kArmHudY+38,
                     static_cast<int>(filled),8,kBattleGold);
  // Keep both rows inside the 84px panel: status at +48 draws through
  // +61; the key hint at +65 draws through +78, before the +80 border.
  battle_text(target,kArmHudX+20,kArmHudY+48,
              magazine.rounds ? "ARM READY" : "ARM EMPTY",
              magazine.rounds ? kBattleGreen : kBattleRed);
  // Switch input discoverability: explicit X and MINUS help is opt-in.
  // 20 glyph cells fit with the final 5x7 character ending at x+277,
  // inside the panel's right border (x+282).
  constexpr char kArmControls[]="X FIRE  MINUS RELOAD";
  static_assert(sizeof(kArmControls)-1 == 20);
  static_assert(20+19*13+10 <= kArmHudWidth-4);
  battle_text(target,kArmHudX+20,kArmHudY+65,
              kArmControls,kBattleWhite);
  return ArmHudStatus::Rendered;
}

} // namespace wa::field
