#pragma once
// Platform-neutral button-edge controller for the synthetic battle prototype.
// Not connected to libnx or exploration events in this stage.
#include "field_battle.hpp"

#include <cstddef>
#include <cstdint>

namespace wa::field {

struct BattlePad {
  bool left = false;
  bool right = false;
  bool up = false;
  bool down = false;
  bool confirm = false;
  bool guard = false;
};

struct BattleCursor {
  std::size_t actor = 0;
  std::size_t target = 0;
  BattlePad previous{};
};

enum class BattleControlStatus : std::uint8_t {
  Idle, CursorMoved, ActionApplied, InvalidState
};

struct BattleControlFrame {
  BattleControlStatus status = BattleControlStatus::Idle;
  BattleUpdate action{};
};

[[nodiscard]] inline bool battle_actor_ready(
    const FieldBattle& b, std::size_t actor) noexcept {
  return actor < kBattlePartySize && b.party[actor].hp > 0 && !b.acted[actor];
}

[[nodiscard]] inline bool battle_target_alive(
    const FieldBattle& b, std::size_t target) noexcept {
  return target < kBattleEnemyCount && b.enemies[target].hp > 0;
}

// Select next available index in either direction, wrapping and skipping
// downed / already-acted participants. The caller guarantees an eligible
// selection exists. No dynamic allocations or mutable global state.
template <std::size_t N, typename Predicate>
[[nodiscard]] inline std::size_t battle_next_index(
    std::size_t selected, int direction, Predicate eligible) noexcept {
  for (std::size_t delta = 1; delta <= N; ++delta) {
    const std::size_t candidate = direction > 0
      ? (selected + delta) % N
      : (selected + N - (delta % N)) % N;
    if (eligible(candidate)) return candidate;
  }
  return selected;
}

// An input frame owns at most one action. Left/Right select an available
// hero, Up/Down select a living enemy; navigation takes priority over A/Y.
// Holding any key never repeats a selection or strike until a new edge.
// Conflicting simultaneous directions and A+Y produce no action.
// Invalid state fails before mutating battle OR cursor (including latches).
[[nodiscard]] inline BattleControlFrame advance_battle_controller(
    FieldBattle& battle, BattleCursor& cursor, const BattlePad& pad) noexcept {
  if (!valid_field_battle(battle) || cursor.actor >= kBattlePartySize ||
      cursor.target >= kBattleEnemyCount)
    return {BattleControlStatus::InvalidState};

  BattleCursor next = cursor;
  const bool left = pad.left && !cursor.previous.left;
  const bool right = pad.right && !cursor.previous.right;
  const bool up = pad.up && !cursor.previous.up;
  const bool down = pad.down && !cursor.previous.down;
  const bool confirm = pad.confirm && !cursor.previous.confirm;
  const bool guard = pad.guard && !cursor.previous.guard;
  next.previous = pad;

  if (battle.phase != BattlePhase::Player) {
    cursor = next;
    return {};
  }

  if (!battle_actor_ready(battle, next.actor))
    next.actor = battle_next_index<kBattlePartySize>(next.actor, +1,
      [&](std::size_t index) { return battle_actor_ready(battle, index); });
  if (!battle_target_alive(battle, next.target))
    next.target = battle_next_index<kBattleEnemyCount>(next.target, +1,
      [&](std::size_t index) { return battle_target_alive(battle, index); });

  const std::size_t old_actor = next.actor;
  const std::size_t old_target = next.target;
  const bool actor_navigation = left != right;
  const bool target_navigation = up != down;
  if (actor_navigation)
    next.actor = battle_next_index<kBattlePartySize>(next.actor,
      right ? +1 : -1,
      [&](std::size_t index) { return battle_actor_ready(battle, index); });
  if (target_navigation)
    next.target = battle_next_index<kBattleEnemyCount>(next.target,
      down ? +1 : -1,
      [&](std::size_t index) { return battle_target_alive(battle, index); });

  if (left || right || up || down) {
    const bool moved = next.actor != old_actor || next.target != old_target;
    cursor = next;
    return {moved ? BattleControlStatus::CursorMoved
                  : BattleControlStatus::Idle};
  }
  if (confirm == guard) {
    cursor = next;
    return {};
  }
  const BattleMove action = guard ? BattleMove::Guard : BattleMove::Strike;
  const BattleUpdate result = advance_field_battle(
      battle, next.actor, action, action == BattleMove::Guard ? 0 : next.target);
  if (result.step != BattleStep::Applied)
    return {BattleControlStatus::InvalidState};

  if (battle.phase == BattlePhase::Player) {
    next.actor = battle_next_index<kBattlePartySize>(next.actor, +1,
      [&](std::size_t index) { return battle_actor_ready(battle, index); });
    if (!battle_target_alive(battle, next.target))
      next.target = battle_next_index<kBattleEnemyCount>(next.target, +1,
        [&](std::size_t index) { return battle_target_alive(battle, index); });
  }
  cursor = next;
  return {BattleControlStatus::ActionApplied, result};
}

}  // namespace wa::field
