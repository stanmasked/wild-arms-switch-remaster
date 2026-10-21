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

// Preview and B-close credit use exactly the same saturating arithmetic.
// A read-only preview cannot mutate the account or the battle. Custom rates
// are a host-side future-proofing seam; default Switch training still uses
// the deliberately synthetic 8 EXP / 12 Gella prototype payout.
[[nodiscard]] constexpr BattleRewardPayout preview_battle_reward(
    const BattleRewardAccount& account, BattleResolution outcome,
    BattleRewardPayout reward={kPrototypeVictoryExp,
                               kPrototypeVictoryGella}) noexcept {
  if (outcome != BattleResolution::Victory) return {};
  return {
      battle_reward_saturating_add(account.experience,reward.experience)
          - account.experience,
      battle_reward_saturating_add(account.gella,reward.gella)
          - account.gella,
  };
}

// Only the validated one-time B closure may call this and update RAM.
[[nodiscard]] inline BattleRewardPayout credit_battle_reward(
    BattleRewardAccount& account, BattleResolution outcome) noexcept {
  const auto paid=preview_battle_reward(account,outcome);
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
