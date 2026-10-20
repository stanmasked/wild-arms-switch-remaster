#pragma once
// Stage 348 — original, asset-free turn result text for the native battle HUD.
// Rendered from a successfully applied BattleUpdate; never affects simulation.
#include "field_battle_view.hpp"

#include <cstdint>
#include <cstdio>

namespace wa::field {

enum class BattleFeedbackKind : std::uint8_t {
  None, Strike, Guard
};

struct BattleFeedback {
  BattleFeedbackKind kind = BattleFeedbackKind::None;
  std::uint16_t damage = 0;
  std::uint32_t enemy_damage = 0;
  bool enemy_turn_completed = false;
};

[[nodiscard]] inline bool valid_battle_feedback(
    const BattleFeedback& feedback) noexcept {
  switch (feedback.kind) {
    case BattleFeedbackKind::None:
      return feedback.damage == 0 && feedback.enemy_damage == 0 &&
             !feedback.enemy_turn_completed;
    case BattleFeedbackKind::Strike:
      return feedback.damage > 0 &&
             (feedback.enemy_turn_completed || feedback.enemy_damage == 0);
    case BattleFeedbackKind::Guard:
      return feedback.damage == 0 &&
             (feedback.enemy_turn_completed || feedback.enemy_damage == 0);
    default:
      return false;
  }
}

[[nodiscard]] inline BattleFeedback battle_feedback_from_action(
    BattleMove move, const BattleUpdate& update) noexcept {
  BattleFeedback result{};
  if (update.step != BattleStep::Applied) return result;
  result.kind = move == BattleMove::Guard
      ? BattleFeedbackKind::Guard : BattleFeedbackKind::Strike;
  result.damage = update.inflicted;
  result.enemy_turn_completed = update.enemy_turn_completed;
  for (const auto loss : update.retaliation)
    result.enemy_damage += loss;
  return result;
}

// The footer's top row (y=648) keeps the static button hints. Put the
// previous turn at y=681. This is independent of the NeXium FPS overlay.
inline void draw_battle_feedback(const PixelTarget& target,
                                 const BattleFeedback& feedback) noexcept {
  if (feedback.kind == BattleFeedbackKind::None ||
      !valid_battle_feedback(feedback)) return;
  char caption[64]{};
  if (feedback.kind == BattleFeedbackKind::Strike) {
    if (feedback.enemy_turn_completed)
      (void)std::snprintf(caption, sizeof(caption),
          "STRIKE %u  ENEMY HIT %u",
          static_cast<unsigned>(feedback.damage),
          static_cast<unsigned>(feedback.enemy_damage));
    else
      (void)std::snprintf(caption, sizeof(caption),
          "STRIKE %u DAMAGE", static_cast<unsigned>(feedback.damage));
  } else {
    if (feedback.enemy_turn_completed)
      (void)std::snprintf(caption, sizeof(caption),
          "GUARD  ENEMY HIT %u",
          static_cast<unsigned>(feedback.enemy_damage));
    else
      (void)std::snprintf(caption, sizeof(caption), "GUARD READY");
  }
  battle_text(target, 70, 682, caption,
              feedback.kind == BattleFeedbackKind::Guard
                  ? kBattleBlue : kBattleGold);
}

} // namespace wa::field
