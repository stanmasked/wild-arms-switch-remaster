#pragma once
// Stage387: host-only opt-in ARM ammunition overlay.
// Not called by Switch main loop; canonical NeXium screenshots unaffected.
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
  battle_text(target,kArmHudX+20,kArmHudY+54,
              magazine.rounds ? "ARM READY" : "ARM EMPTY",
              magazine.rounds ? kBattleGreen : kBattleRed);
  return ArmHudStatus::Rendered;
}

} // namespace wa::field
