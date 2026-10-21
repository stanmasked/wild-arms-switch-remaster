#include "field_battle_arm.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <limits>

using namespace wa::field;

namespace {

void equal_battle(const FieldBattle& a, const FieldBattle& b) {
  assert(a.phase == b.phase && a.round == b.round);
  for (std::size_t i=0;i<kBattlePartySize;++i) {
    assert(a.party[i].hp == b.party[i].hp);
    assert(a.party[i].max_hp == b.party[i].max_hp);
    assert(a.party[i].attack == b.party[i].attack);
    assert(a.party[i].armor == b.party[i].armor);
    assert(a.acted[i] == b.acted[i] && a.guarding[i] == b.guarding[i]);
  }
  for (std::size_t i=0;i<kBattleEnemyCount;++i) {
    assert(a.enemies[i].hp == b.enemies[i].hp);
    assert(a.enemies[i].max_hp == b.enemies[i].max_hp);
    assert(a.enemies[i].attack == b.enemies[i].attack);
    assert(a.enemies[i].armor == b.enemies[i].armor);
  }
}

void arm_fire_uses_real_turn_and_restores_melee_stats() {
  auto b = make_demo_battle();
  ArmMagazine arm{};
  const auto melee_attack = b.party[0].attack;
  const auto shot = advance_arm_command(b, arm, 0, ArmCommand::Fire, 0);
  assert(shot.step == ArmStep::Applied);
  assert(shot.battle.step == BattleStep::Applied);
  assert(shot.battle.inflicted == 9); // 10 ARM attack - 1 armor
  assert(!shot.battle.enemy_turn_completed);
  assert(b.enemies[0].hp == 5 && b.acted[0]);
  assert(b.party[0].attack == melee_attack && arm.rounds == 2);
  const auto frozen=b;
  const auto ammo=arm.rounds;
  assert(advance_arm_command(b,arm,0,ArmCommand::Fire,0).step ==
         ArmStep::InvalidChoice);
  assert(arm.rounds == ammo);
  equal_battle(b,frozen);
}

void ammo_empty_rejected_then_reload_consumes_turn_without_guard() {
  auto b = make_demo_battle();
  ArmMagazine arm{1,3,10};
  assert(advance_arm_command(b,arm,0,ArmCommand::Fire,0).step ==
         ArmStep::Applied);
  assert(arm.rounds == 0);
  assert(advance_field_battle(b,1,BattleMove::Guard).step ==
         BattleStep::Applied);
  assert(advance_field_battle(b,2,BattleMove::Guard).enemy_turn_completed);
  assert(b.round == 2);
  const auto original=b;
  assert(advance_arm_command(b,arm,0,ArmCommand::Fire,0).step == ArmStep::Empty);
  equal_battle(b,original);
  assert(arm.rounds == 0);
  auto reload=advance_arm_command(b,arm,0,ArmCommand::Reload);
  assert(reload.step == ArmStep::Applied && !reload.battle.enemy_turn_completed);
  assert(b.acted[0] && !b.guarding[0]); // Not equivalent to Y Guard.
  assert(arm.rounds == 3 && b.round == 2);
  const auto after_reload=b;
  assert(advance_arm_command(b,arm,0,ArmCommand::Reload).step ==
         ArmStep::InvalidChoice);
  equal_battle(b,after_reload);
}

void no_reload_at_full_capacity_or_on_wrong_target() {
  auto b=make_demo_battle();
  ArmMagazine arm{};
  const auto before=b;
  assert(advance_arm_command(b,arm,0,ArmCommand::Reload).step ==
         ArmStep::AlreadyFull);
  assert(advance_arm_command(b,arm,0,ArmCommand::Reload,1).step ==
         ArmStep::InvalidChoice);
  assert(advance_arm_command(b,arm,1,ArmCommand::Fire,0).step ==
         ArmStep::InvalidChoice);
  assert(advance_arm_command(b,arm,0,ArmCommand::Fire,9).step ==
         ArmStep::InvalidChoice);
  assert(arm.rounds==3);
  equal_battle(b,before);
}

void victory_finishing_shot_never_grants_enemy_retaliation() {
  auto b=make_demo_battle();
  ArmMagazine arm{};
  b.enemies[0].hp=1;
  b.enemies[1].hp=1;
  const auto r=advance_arm_command(b,arm,0,ArmCommand::Fire,0);
  assert(r.step==ArmStep::Applied && r.battle.inflicted==1);
  assert(arm.rounds==2 && b.party[0].attack==7);
  const auto finish=advance_field_battle(b,1,BattleMove::Strike,1);
  assert(finish.phase==BattlePhase::Victory);
  assert(!finish.enemy_turn_completed && b.party[0].hp==24);
  const auto frozen=b;
  assert(advance_arm_command(b,arm,0,ArmCommand::Reload).step ==
         ArmStep::InvalidChoice);
  equal_battle(b,frozen);
  assert(arm.rounds==2);
}

void corrupted_magazine_and_invalid_command_fail_atomically() {
  for(const auto mag: {ArmMagazine{4,3,10}, ArmMagazine{0,0,10},
                       ArmMagazine{2,3,0}}) {
    auto b=make_demo_battle();
    auto arm=mag;
    const auto old=b;
    assert(advance_arm_command(b,arm,0,ArmCommand::Fire,0).step ==
           ArmStep::InvalidState);
    equal_battle(b,old);
    assert(arm.rounds==mag.rounds && arm.capacity==mag.capacity);
  }
  auto b=make_demo_battle();ArmMagazine arm{};
  const auto old=b;
  assert(advance_arm_command(b,arm,0,static_cast<ArmCommand>(55)).step ==
         ArmStep::InvalidChoice);
  equal_battle(b,old);
  assert(arm.rounds==3);
  b.round=0;
  assert(advance_arm_command(b,arm,0,ArmCommand::Fire).step ==
         ArmStep::InvalidState);
}

void overflow_rolls_back_last_round_without_extra_bullets() {
  auto b=make_demo_battle();
  ArmMagazine arm{1,3,10};
  b.round=std::numeric_limits<std::uint32_t>::max();
  assert(advance_arm_command(b,arm,0,ArmCommand::Reload).step == ArmStep::Applied);
  assert(arm.rounds==3);
  assert(advance_field_battle(b,1,BattleMove::Guard).step==BattleStep::Applied);
  const auto old=b;
  const auto result=advance_field_battle(b,2,BattleMove::Reload);
  assert(result.step==BattleStep::InvalidState);
  equal_battle(b,old);
  assert(arm.rounds==3);
}

void burst_consumes_two_bullets_for_one_real_finishing_turn() {
  auto b=make_demo_battle();ArmMagazine mag{};
  const auto before=b.party[0].attack;
  const auto shot=advance_arm_command(b,mag,0,ArmCommand::Burst,0);
  assert(shot.step==ArmStep::Applied && shot.battle.step==BattleStep::Applied);
  assert(shot.battle.inflicted==14); // (10 + 5) - armor 1
  assert(b.enemies[0].hp==0 && b.enemies[1].hp==17);
  assert(b.acted[0] && b.phase==BattlePhase::Player);
  assert(mag.rounds==1 && b.party[0].attack==before);
  assert(!shot.battle.enemy_turn_completed);
}

void burst_rejects_one_round_without_losing_turn_or_stat() {
  auto b=make_demo_battle();ArmMagazine mag{1,3,10};
  const auto original=b;
  const auto result=advance_arm_command(b,mag,0,ArmCommand::Burst,0);
  assert(result.step==ArmStep::InsufficientAmmo);
  assert(mag.rounds==1 && !b.acted[0]);
  equal_battle(b,original);
  mag.rounds=0;
  assert(advance_arm_command(b,mag,0,ArmCommand::Burst,0).step==ArmStep::Empty);
  equal_battle(b,original);
}

void burst_overflow_is_saturated_and_never_mutates_melee() {
  auto b=make_demo_battle();ArmMagazine mag{2,3,65535};
  const auto melee=b.party[0].attack;
  const auto shot=advance_arm_command(b,mag,0,ArmCommand::Burst,1);
  assert(shot.step==ArmStep::Applied);
  assert(shot.battle.inflicted==17 && b.enemies[1].hp==0);
  assert(b.party[0].attack==melee && mag.rounds==0);
}

void burst_failed_round_transition_preserves_bullet_count() {
  auto b=make_demo_battle();ArmMagazine mag{3,3,10};
  b.round=std::numeric_limits<std::uint32_t>::max();
  assert(advance_field_battle(b,1,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(b,2,BattleMove::Guard).step==BattleStep::Applied ||
         b.phase!=BattlePhase::Player);
  // Fresh actor on overflow cannot apply, and rollback is atomic.
  auto next=make_demo_battle();ArmMagazine next_mag{2,3,10};
  next.round=std::numeric_limits<std::uint32_t>::max();
  next.acted[1]=true;next.acted[2]=true;
  const auto old=next;
  const auto out=advance_arm_command(next,next_mag,0,ArmCommand::Burst,0);
  assert(out.step==ArmStep::InvalidState);
  assert(next_mag.rounds==2);
  equal_battle(next,old);
}

} // namespace

int main() {
  arm_fire_uses_real_turn_and_restores_melee_stats();
  ammo_empty_rejected_then_reload_consumes_turn_without_guard();
  no_reload_at_full_capacity_or_on_wrong_target();
  victory_finishing_shot_never_grants_enemy_retaliation();
  corrupted_magazine_and_invalid_command_fail_atomically();
  overflow_rolls_back_last_round_without_extra_bullets();
  burst_consumes_two_bullets_for_one_real_finishing_turn();
  burst_rejects_one_round_without_losing_turn_or_stat();
  burst_overflow_is_saturated_and_never_mutates_melee();
  burst_failed_round_transition_preserves_bullet_count();
}
