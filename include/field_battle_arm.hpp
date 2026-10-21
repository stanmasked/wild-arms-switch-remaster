#pragma once
// Stage385: asset-free, opt-in ARM firearm/ammunition experiment.
// Deliberately NOT wired to the old A/Y controller, field runtime, WABJ
// journal or Nintendo Switch NRO. Save schema v1 remains byte-identical.
#include "field_battle.hpp"

#include <cstddef>
#include <cstdint>
#include <limits>

namespace wa::field {

constexpr std::size_t kPrototypeArmActor = 0;

// Experimental ARM values, not reconstructed PlayStation balance data.
struct ArmMagazine {
  std::uint8_t rounds = 3;
  std::uint8_t capacity = 3;
  std::uint16_t shot_attack = 10;
};

enum class ArmCommand : std::uint8_t { Fire, Reload, Burst };
enum class ArmStep : std::uint8_t {
  Applied, InvalidState, InvalidChoice, Empty, AlreadyFull, InsufficientAmmo
};
struct ArmUpdate {
  ArmStep step = ArmStep::InvalidState;
  BattleUpdate battle{};
};

[[nodiscard]] constexpr bool valid_arm_magazine(
    const ArmMagazine& arm) noexcept {
  return arm.capacity > 0 && arm.rounds <= arm.capacity &&
         arm.shot_attack > 0;
}

// A real Fire uses the normal deterministic Strike round / retaliation
// path but with temporary ARM attack power. The hero's melee attack
// stat is restored BEFORE publishing the new battle state.
// Reload consumes one normal turn with NO guard reduction, unlike the
// separate Y Guard action. All rejected operations are fully atomic.
[[nodiscard]] inline ArmUpdate advance_arm_command(
    FieldBattle& current, ArmMagazine& magazine, std::size_t actor,
    ArmCommand command, std::size_t target=0) noexcept {
  if (!valid_field_battle(current) || !valid_arm_magazine(magazine))
    return {ArmStep::InvalidState};
  if (current.phase != BattlePhase::Player ||
      actor != kPrototypeArmActor || current.party[actor].hp==0 ||
      current.acted[actor] ||
      (command!=ArmCommand::Fire && command!=ArmCommand::Reload &&
       command!=ArmCommand::Burst))
    return {ArmStep::InvalidChoice};
  if (command==ArmCommand::Fire || command==ArmCommand::Burst) {
    if (target>=kBattleEnemyCount || current.enemies[target].hp==0)
      return {ArmStep::InvalidChoice};
    if (magazine.rounds==0) return {ArmStep::Empty};
    if (command==ArmCommand::Burst && magazine.rounds<2)
      return {ArmStep::InsufficientAmmo};
  } else {
    if (target!=0) return {ArmStep::InvalidChoice};
    if (magazine.rounds==magazine.capacity) return {ArmStep::AlreadyFull};
  }

  FieldBattle next=current;
  ArmMagazine next_magazine=magazine;
  BattleUpdate result{};
  if (command==ArmCommand::Fire || command==ArmCommand::Burst) {
    const auto melee_attack=next.party[actor].attack;
    // Experimental charged burst costs 2 ammo for a +5 attack power
    // finishing strike (ordinary single-bullet Fire remains untouched).
    const std::uint32_t attack=static_cast<std::uint32_t>(
        next_magazine.shot_attack)+
        (command==ArmCommand::Burst ? 5u : 0u);
    next.party[actor].attack=static_cast<std::uint16_t>(
        attack>std::numeric_limits<std::uint16_t>::max()
          ? std::numeric_limits<std::uint16_t>::max() : attack);
    result=advance_field_battle(next,actor,BattleMove::Strike,target);
    next.party[actor].attack=melee_attack;
    if (result.step==BattleStep::Applied)
      next_magazine.rounds=static_cast<std::uint8_t>(
          next_magazine.rounds - (command==ArmCommand::Burst ? 2u : 1u));
  } else {
    result=advance_field_battle(next,actor,BattleMove::Reload);
    if (result.step==BattleStep::Applied)
      next_magazine.rounds=next_magazine.capacity;
  }
  if (result.step!=BattleStep::Applied) return {ArmStep::InvalidState,result};
  current=next;
  magazine=next_magazine;
  return {ArmStep::Applied,result};
}

} // namespace wa::field
