#pragma once
// Stage 357: deterministic ROM-free rewards. No original-game economy data.
// Rewards are volatile until a separate versioned save feature is approved.
#include "field_battle_results.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>

namespace wa::field {

constexpr std::uint32_t kPrototypeVictoryExp = 8;
constexpr std::uint32_t kPrototypeVictoryGella = 12;

struct BattleRewardAccount {
  std::uint32_t experience = 0;
  std::uint32_t gella = 0;
};

struct BattleRewardPayout {
  std::uint32_t experience = 0;
  std::uint32_t gella = 0;
};

[[nodiscard]] constexpr std::uint32_t battle_reward_saturating_add(
    std::uint32_t a, std::uint32_t b) noexcept {
  return b > std::numeric_limits<std::uint32_t>::max() - a
      ? std::numeric_limits<std::uint32_t>::max() : a + b;
}

// May be called only by the already-validated one-time B closure.
// EXP / Gella are synthetic placeholders until PS1 combat data exists.
// Return the *actually credited* value (important near saturation).
[[nodiscard]] inline BattleRewardPayout credit_battle_reward(
    BattleRewardAccount& account, BattleResolution outcome) noexcept {
  if (outcome != BattleResolution::Victory) return {};
  const auto new_exp = battle_reward_saturating_add(
      account.experience, kPrototypeVictoryExp);
  const auto new_gella = battle_reward_saturating_add(
      account.gella, kPrototypeVictoryGella);
  const BattleRewardPayout paid{new_exp-account.experience,
                                new_gella-account.gella};
  account.experience = new_exp;
  account.gella = new_gella;
  return paid;
}

// Display is only ever invoked inside the already explicitly ZL-held
// history panel, so ordinary field and battle screenshots remain stable.
inline void draw_battle_reward_balance(
    const PixelTarget& target, const BattleRewardAccount& account) noexcept {
  char line[64]{};
  (void)std::snprintf(line,sizeof(line),"EXP %u  G %u",
      static_cast<unsigned>(account.experience),
      static_cast<unsigned>(account.gella));
  battle_text(target,961,623,line,kBattleGreen);
}

}  // namespace wa::field
