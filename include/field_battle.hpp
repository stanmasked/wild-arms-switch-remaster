#pragma once
// Synthetic host/Switch-portable battle prototype; no PS1 assets or saves.
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace wa::field {
constexpr std::size_t kBattlePartySize = 3;
constexpr std::size_t kBattleEnemyCount = 2;
struct BattleFighter {
  std::uint16_t hp=0, max_hp=0, attack=0, armor=0;
};
enum class BattlePhase : std::uint8_t { Player, Victory, Defeat };
enum class BattleMove : std::uint8_t { Strike, Guard };
struct FieldBattle {
  std::array<BattleFighter, kBattlePartySize> party{};
  std::array<BattleFighter, kBattleEnemyCount> enemies{};
  std::array<bool, kBattlePartySize> acted{}, guarding{};
  BattlePhase phase = BattlePhase::Player;
  std::uint32_t round = 1;
};
enum class BattleStep : std::uint8_t { Applied, InvalidState, InvalidChoice };
struct BattleUpdate {
  BattleStep step = BattleStep::InvalidState;
  BattlePhase phase = BattlePhase::Player;
  bool enemy_turn_completed = false;
  std::uint16_t inflicted = 0;
  std::array<std::uint16_t, kBattlePartySize> retaliation{};
};
[[nodiscard]] inline bool battle_fighter_valid(const BattleFighter& f) noexcept {
  return f.max_hp > 0 && f.hp <= f.max_hp;
}
template <std::size_t N>
[[nodiscard]] inline bool battle_any_living(
    const std::array<BattleFighter, N>& fighters) noexcept {
  for (const auto& f : fighters) if (f.hp) return true;
  return false;
}
[[nodiscard]] inline bool valid_field_battle(const FieldBattle& b) noexcept {
  if (!b.round) return false;
  for (const auto& f : b.party) if (!battle_fighter_valid(f)) return false;
  for (const auto& f : b.enemies) if (!battle_fighter_valid(f)) return false;
  for (std::size_t i=0; i<kBattlePartySize; ++i)
    if (b.guarding[i] && !b.acted[i]) return false;
  const bool p=battle_any_living(b.party), e=battle_any_living(b.enemies);
  switch (b.phase) {
    case BattlePhase::Player: return p && e;
    case BattlePhase::Victory: return p && !e;
    case BattlePhase::Defeat: return !p && e;
    default: return false;
  }
}
[[nodiscard]] inline FieldBattle make_demo_battle() noexcept {
  FieldBattle b{};
  b.party = {{{24,24,7,2},{20,20,6,1},{18,18,5,3}}};
  b.enemies = {{{14,14,5,1},{17,17,6,2}}};
  return b;
}
[[nodiscard]] inline std::uint16_t battle_damage(
    std::uint16_t attack, std::uint16_t armor, bool guard) noexcept {
  const std::uint32_t base=attack>armor ? static_cast<std::uint32_t>(attack-armor) : 1u;
  return static_cast<std::uint16_t>(guard ? (base+1u)/2u : base);
}
// Invalid commands never write to the caller's state. All choices are
// deterministic, with no randomness, file I/O or platform dependencies.
[[nodiscard]] inline BattleUpdate advance_field_battle(
    FieldBattle& current, std::size_t actor, BattleMove move,
    std::size_t target=0) noexcept {
  if (!valid_field_battle(current))
    return {BattleStep::InvalidState,current.phase};
  if (current.phase!=BattlePhase::Player || actor>=kBattlePartySize ||
      current.party[actor].hp==0 || current.acted[actor] ||
      (move!=BattleMove::Strike && move!=BattleMove::Guard) ||
      (move==BattleMove::Strike &&
       (target>=kBattleEnemyCount || current.enemies[target].hp==0)) ||
      (move==BattleMove::Guard && target!=0))
    return {BattleStep::InvalidChoice,current.phase};
  FieldBattle next=current;
  BattleUpdate result{BattleStep::Applied,current.phase};
  next.acted[actor]=true;
  if (move==BattleMove::Guard) {
    next.guarding[actor]=true;
  } else {
    auto& enemy=next.enemies[target];
    const auto nominal=battle_damage(next.party[actor].attack,enemy.armor,false);
    result.inflicted=nominal<enemy.hp ? nominal : enemy.hp;
    enemy.hp=static_cast<std::uint16_t>(enemy.hp-result.inflicted);
  }
  if (!battle_any_living(next.enemies)) {
    next.phase=BattlePhase::Victory;
    result.phase=next.phase;
    current=next;
    return result; // No retaliation after winning strike.
  }
  for (std::size_t i=0; i<kBattlePartySize; ++i)
    if (next.party[i].hp && !next.acted[i]) {
      current=next;
      return result;
    }
  result.enemy_turn_completed=true;
  for (std::size_t enemy=0; enemy<kBattleEnemyCount; ++enemy) {
    if (!next.enemies[enemy].hp || !battle_any_living(next.party)) continue;
    const auto initial=static_cast<std::size_t>(
        (next.round-1u+enemy)%kBattlePartySize);
    for (std::size_t offset=0; offset<kBattlePartySize; ++offset) {
      const auto i=(initial+offset)%kBattlePartySize;
      auto& hero=next.party[i];
      if (!hero.hp) continue;
      const auto nominal=battle_damage(
          next.enemies[enemy].attack,hero.armor,next.guarding[i]);
      const auto loss=nominal<hero.hp ? nominal : hero.hp;
      hero.hp=static_cast<std::uint16_t>(hero.hp-loss);
      result.retaliation[i]=static_cast<std::uint16_t>(result.retaliation[i]+loss);
      break;
    }
  }
  if (!battle_any_living(next.party)) {
    next.phase=BattlePhase::Defeat;
  } else {
    // No rollover and no partial state publication if the limit is hit.
    if (next.round==std::numeric_limits<std::uint32_t>::max())
      return {BattleStep::InvalidState,current.phase};
    ++next.round;
    next.acted.fill(false);
    next.guarding.fill(false);
  }
  result.phase=next.phase;
  current=next;
  return result;
}
}  // namespace wa::field
