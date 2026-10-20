#pragma once
// Stage386: optional edge-only ARM input adapter for host simulations.
// NOT wired into Switch controls or WABJ; no change to A/Y battle mapping.
#include "field_battle_arm.hpp"
#include "field_battle_controller.hpp"

#include <cstddef>
#include <cstdint>

namespace wa::field {

struct ArmButtons {
  bool fire = false;
  bool reload = false;
};

struct ArmEdgeState {
  ArmButtons previous{};
};

enum class ArmControlStatus : std::uint8_t {
  Idle, Applied, Refused, InvalidState
};

struct ArmControlFrame {
  ArmControlStatus status = ArmControlStatus::Idle;
  ArmUpdate update{};
};

// A new physical edge is necessary for each Fire or Reload. Holding a
// button never fires again on the next frame or after a round ends.
// Conflicting held Fire+Reload consumes both edges without side effects.
// Navigation remains under the existing BattleCursor; this adapter never
// invents an actor selection or changes ordinary A/Y latch history.
[[nodiscard]] inline ArmControlFrame advance_arm_controller(
    FieldBattle& battle, ArmMagazine& magazine,
    BattleCursor& cursor, ArmEdgeState& state,
    const ArmButtons& buttons) noexcept {
  if (!valid_field_battle(battle) || !valid_arm_magazine(magazine) ||
      cursor.actor >= kBattlePartySize ||
      cursor.target >= kBattleEnemyCount)
    return {ArmControlStatus::InvalidState};

  ArmEdgeState next_state=state;
  next_state.previous=buttons;
  const bool fire_edge=buttons.fire && !state.previous.fire;
  const bool reload_edge=buttons.reload && !state.previous.reload;
  if ((buttons.fire && buttons.reload) || fire_edge == reload_edge) {
    state=next_state;
    return {};
  }

  const bool fire=fire_edge;
  // A stale target is repaired ONLY if the ARM action commits, and
  // never allows shooting a dead enemy when all enemies are dead.
  std::size_t target=cursor.target;
  if (fire && !battle_target_alive(battle,target))
    target=battle_next_index<kBattleEnemyCount>(
        target,+1,[&](std::size_t i){ return battle_target_alive(battle,i); });

  const ArmUpdate outcome=advance_arm_command(
      battle,magazine,cursor.actor,
      fire ? ArmCommand::Fire : ArmCommand::Reload,
      fire ? target : 0);
  state=next_state;
  if (outcome.step!=ArmStep::Applied)
    return {ArmControlStatus::Refused,outcome};

  BattleCursor updated=cursor;
  if (fire) updated.target=target;
  if (battle.phase==BattlePhase::Player) {
    updated.actor=battle_next_index<kBattlePartySize>(
        updated.actor,+1,
        [&](std::size_t i){return battle_actor_ready(battle,i);});
    if (!battle_target_alive(battle,updated.target))
      updated.target=battle_next_index<kBattleEnemyCount>(
          updated.target,+1,
          [&](std::size_t i){return battle_target_alive(battle,i);});
  }
  cursor=updated;
  return {ArmControlStatus::Applied,outcome};
}

} // namespace wa::field
