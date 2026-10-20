#pragma once
// Stage 355: volatile, opt-in battle outcome history and read-only HUD.
// No PlayStation assets and no changes to exploration save files.
#include "field_battle_view.hpp"

#include <cstdint>
#include <cstdio>
#include <limits>

namespace wa::field {

enum class BattleResolution : std::uint8_t {
  None, Victory, Defeat, Retreat
};

struct BattleHistory {
  std::uint32_t victories = 0;
  std::uint32_t defeats = 0;
  std::uint32_t retreats = 0;
  BattleResolution last = BattleResolution::None;
};

[[nodiscard]] constexpr BattleResolution battle_resolution(
    BattlePhase phase) noexcept {
  switch (phase) {
    case BattlePhase::Victory: return BattleResolution::Victory;
    case BattlePhase::Defeat: return BattleResolution::Defeat;
    case BattlePhase::Player: return BattleResolution::Retreat;
  }
  return BattleResolution::None;
}

// Only called on a validated B-close transition. No counter wraps after
// UINT32_MAX, and a completed result can never be recorded twice.
[[nodiscard]] inline BattleResolution record_battle_exit(
    BattleHistory& history, BattlePhase phase) noexcept {
  const auto outcome = battle_resolution(phase);
  std::uint32_t* counter = nullptr;
  switch (outcome) {
    case BattleResolution::Victory: counter = &history.victories; break;
    case BattleResolution::Defeat: counter = &history.defeats; break;
    case BattleResolution::Retreat: counter = &history.retreats; break;
    case BattleResolution::None: return outcome;
  }
  if (*counter < std::numeric_limits<std::uint32_t>::max()) ++*counter;
  history.last = outcome;
  return outcome;
}

[[nodiscard]] constexpr const char* battle_last_result(
    BattleResolution last) noexcept {
  switch (last) {
    case BattleResolution::None: return "NONE";
    case BattleResolution::Victory: return "VICTORY";
    case BattleResolution::Defeat: return "DEFEAT";
    case BattleResolution::Retreat: return "RETREAT";
  }
  return "NONE";
}

// Drawn ONLY on request by holding ZL while manually exploring.
// A normal field frame (including B return) is completely unchanged.
[[nodiscard]] inline bool draw_field_battle_history(
    const PixelTarget& target, const BattleHistory& history) noexcept {
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight || target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192) return false;

  fill_raster_rect(target,690,612,550,96,kBattlePanel);
  battle_outline(target,690,612,550,96,kBattleGold);
  battle_text(target,711,623,"BATTLE RESULTS",kBattleWhite);
  char line[64]{};
  (void)std::snprintf(line,sizeof(line),"WINS %u  LOSSES %u",
      static_cast<unsigned>(history.victories),
      static_cast<unsigned>(history.defeats));
  battle_text(target,711,650,line,kBattleGold);
  (void)std::snprintf(line,sizeof(line),"EXITS %u  LAST %s",
      static_cast<unsigned>(history.retreats),
      battle_last_result(history.last));
  battle_text(target,711,677,line,kBattleWhite);
  return true;
}

// Subtle record on later battle screens, without changing the first fight
// or the baseline NeXium R/ZR screenshot checks.
inline void draw_previous_battle_history(
    const PixelTarget& target, const BattleHistory& history) noexcept {
  if (history.last == BattleResolution::None) return;
  char line[64]{};
  (void)std::snprintf(line,sizeof(line),"W %u  L %u  E %u",
      static_cast<unsigned>(history.victories),
      static_cast<unsigned>(history.defeats),
      static_cast<unsigned>(history.retreats));
  battle_text(target,70,687,line,kBattleGold);
}

}  // namespace wa::field
