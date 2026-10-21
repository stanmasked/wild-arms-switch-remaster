#pragma once
// Stage 357/404: deterministic ROM-free prototype rewards, not original-game economy data.
// Persistence is owned by separate versioned journals, never by this account type.
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

// Source of truth for a pending reward. Pure, no account mutation.
// The optional in-memory offer supports future prototype balancing;
// the default preserves the already validated 8 EXP / 12 Gella.
// Preview is exactly the ACTUAL possible credit even near UINT32_MAX.
[[nodiscard]] constexpr BattleRewardPayout preview_battle_reward(
    const BattleRewardAccount& account, BattleResolution outcome,
    BattleRewardPayout offer={
        kPrototypeVictoryExp,kPrototypeVictoryGella}) noexcept {
  if (outcome!=BattleResolution::Victory) return {};
  const auto exp=battle_reward_saturating_add(account.experience,offer.experience);
  const auto gella=battle_reward_saturating_add(account.gella,offer.gella);
  return {exp-account.experience,gella-account.gella};
}

// Called only by validated one-time B closure; uses exactly the same
// pure preview rule as the Victory UI, never a parallel fixed literal.
[[nodiscard]] inline BattleRewardPayout credit_battle_reward(
    BattleRewardAccount& account, BattleResolution outcome,
    BattleRewardPayout offer={
        kPrototypeVictoryExp,kPrototypeVictoryGella}) noexcept {
  const auto paid=preview_battle_reward(account,outcome,offer);
  account.experience+=paid.experience;
  account.gella+=paid.gella;
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
