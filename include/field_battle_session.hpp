#pragma once
// Stage 341: explicit opt-in battle screen, isolated from exploration saves.
// This is a synthetic demonstration battle, not a reconstructed PS1 encounter.
#include "field_battle_view.hpp"

#include <cstdint>

namespace wa::field {

struct FieldBattleSession {
  FieldBattle battle = make_demo_battle();
  BattleCursor cursor{};
  bool active = false;
};

struct FieldBattleSessionInput {
  bool open = false;      // Switch R rising edge, manual mode only
  bool close = false;     // Switch B rising edge while battle is active
  bool manual_mode = false;
  BattlePad pad{};        // sampled D-pad, A strike, Y guard
};

enum class BattleSceneStatus : std::uint8_t {
  Inactive, Rendered, InvalidTarget, InvalidBattle, InvalidController
};

struct BattleSceneFrame {
  BattleSceneStatus status = BattleSceneStatus::Inactive;
  bool entered = false;
  bool exited = false;
  BattleControlFrame control{};
};

// Executes one battle-only frame after the field engine has sampled a
// neutral controller. On failures, neither the session nor its cursor
// edge latches are modified. The framebuffer renderer itself validates
// before drawing any pixel. No save file or field world is touched.
[[nodiscard]] inline BattleSceneFrame advance_battle_session(
    FieldBattleSession& current, const FieldBattleSessionInput& input,
    const PixelTarget& target) noexcept {
  if (!current.active &&
      (!input.open || !input.manual_mode || input.close))
    return {};

  FieldBattleSession next = current;
  const bool entering = !current.active;
  if (entering) {
    next.battle = make_demo_battle();
    next.cursor = BattleCursor{};
    // Input used to open the scene must be released before it can
    // trigger an attack/navigation. Do not consume a held A press.
    next.cursor.previous = input.pad;
    next.active = true;
  } else {
    if (!valid_field_battle(next.battle) ||
        next.cursor.actor >= kBattlePartySize ||
        next.cursor.target >= kBattleEnemyCount)
      return {BattleSceneStatus::InvalidBattle};
    if (input.close) {
      next.active = false;
      current = next;
      return {BattleSceneStatus::Inactive, false, true};
    }
  }

  BattleSceneFrame result{};
  if (!entering) {
    result.control = advance_battle_controller(
        next.battle, next.cursor, input.pad);
    if (result.control.status == BattleControlStatus::InvalidState)
      return {BattleSceneStatus::InvalidController};
  }
  const BattleRenderStatus drawn =
      draw_field_battle(target, next.battle, next.cursor);
  if (drawn != BattleRenderStatus::Rendered)
    return {drawn == BattleRenderStatus::InvalidTarget
               ? BattleSceneStatus::InvalidTarget
               : BattleSceneStatus::InvalidBattle};

  current = next;
  result.status = BattleSceneStatus::Rendered;
  result.entered = entering;
  return result;
}

}  // namespace wa::field
