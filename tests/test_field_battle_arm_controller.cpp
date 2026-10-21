#include "field_battle_arm_controller.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>

using namespace wa::field;

namespace {

void release(FieldBattle& battle, ArmMagazine& mag, BattleCursor& cursor,
             ArmEdgeState& edge) {
  const auto update=advance_arm_controller(battle,mag,cursor,edge,{});
  assert(update.status==ArmControlStatus::Idle);
}

void held_fire_cannot_repeat_or_attack_next_actor() {
  auto b=make_demo_battle();ArmMagazine mag{};BattleCursor cursor{};
  ArmEdgeState edges{};
  cursor.previous.confirm=true; // Existing A/Y latch cannot be reset here.
  const ArmButtons fire{true,false};
  auto r=advance_arm_controller(b,mag,cursor,edges,fire);
  assert(r.status==ArmControlStatus::Applied && r.update.battle.inflicted==9);
  assert(mag.rounds==2 && b.enemies[0].hp==5 && cursor.actor==1);
  assert(cursor.previous.confirm);
  const auto state=b;
  for(int i=0;i<8;++i)
    assert(advance_arm_controller(b,mag,cursor,edges,fire).status==
           ArmControlStatus::Idle);
  assert(b.enemies[0].hp==state.enemies[0].hp && mag.rounds==2);
  release(b,mag,cursor,edges);
  r=advance_arm_controller(b,mag,cursor,edges,fire);
  assert(r.status==ArmControlStatus::Refused);
  assert(r.update.step==ArmStep::InvalidChoice);
  assert(mag.rounds==2 && b.enemies[0].hp==5); // Actor 1 owns this turn.
}

void simultaneous_fire_and_reload_never_fires_on_release() {
  auto b=make_demo_battle();ArmMagazine mag{};BattleCursor cursor{};
  ArmEdgeState edges{};
  assert(advance_arm_controller(b,mag,cursor,edges,{true,true}).status==
         ArmControlStatus::Idle);
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::Idle);
  assert(b.enemies[0].hp==14 && mag.rounds==3);
  release(b,mag,cursor,edges);
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::Applied);
  assert(b.enemies[0].hp==5 && mag.rounds==2);
}

void reload_uses_normal_turn_and_never_grants_guard() {
  auto b=make_demo_battle();ArmMagazine mag{1,3,10};
  BattleCursor cursor{};ArmEdgeState edges{};
  const ArmButtons reload{false,true};
  const auto r=advance_arm_controller(b,mag,cursor,edges,reload);
  assert(r.status==ArmControlStatus::Applied);
  assert(r.update.battle.inflicted==0);
  assert(b.acted[0] && !b.guarding[0] && mag.rounds==3);
  assert(cursor.actor==1);
  assert(advance_arm_controller(b,mag,cursor,edges,reload).status==
         ArmControlStatus::Idle);
  assert(advance_field_battle(b,1,BattleMove::Guard).step==BattleStep::Applied);
  const auto end=advance_field_battle(b,2,BattleMove::Guard);
  assert(end.step==BattleStep::Applied && end.enemy_turn_completed);
  assert(b.round==2 && b.party[0].hp==21); // Unprotected: 5 ATK - 2 armor.
  assert(b.party[1].hp==17); // Guarded: (6 ATK - 1 armor + 1)/2.
  release(b,mag,cursor,edges);
  cursor.actor=0;
  const auto full=advance_arm_controller(b,mag,cursor,edges,reload);
  assert(full.status==ArmControlStatus::Refused);
  assert(full.update.step==ArmStep::AlreadyFull);
}

void stale_dead_target_is_repaired_only_on_successful_fire() {
  auto b=make_demo_battle();ArmMagazine mag{};
  BattleCursor cursor{};ArmEdgeState edges{};
  b.enemies[0].hp=0; b.enemies[1].hp=1;cursor.target=0;
  auto r=advance_arm_controller(b,mag,cursor,edges,{true,false});
  assert(r.status==ArmControlStatus::Applied);
  assert(r.update.battle.phase==BattlePhase::Victory);
  assert(cursor.target==1 && b.enemies[1].hp==0);
  assert(mag.rounds==2 && b.party[0].hp==24);
  release(b,mag,cursor,edges);
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::Refused);
  assert(mag.rounds==2);
}

void rejected_empty_magazine_leaves_cursor_battle_and_melee_untouched() {
  auto b=make_demo_battle();ArmMagazine mag{0,3,10};
  BattleCursor cursor{};ArmEdgeState edges{};
  cursor.previous.guard=true;
  const auto old=b;
  const auto result=advance_arm_controller(b,mag,cursor,edges,{true,false});
  assert(result.status==ArmControlStatus::Refused);
  assert(result.update.step==ArmStep::Empty);
  assert(mag.rounds==0 && b.enemies[0].hp==old.enemies[0].hp);
  assert(!b.acted[0] && cursor.actor==0 && cursor.target==0);
  assert(cursor.previous.guard && edges.previous.fire);
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::Idle);
}

void corrupt_state_does_not_consume_fire_edge_or_ammo() {
  auto b=make_demo_battle();ArmMagazine mag{};BattleCursor cursor{};
  ArmEdgeState edges{};
  b.party[0].hp=25; // Beyond max HP.
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::InvalidState);
  assert(!edges.previous.fire && mag.rounds==3);
  b.party[0].hp=24;
  cursor.target=kBattleEnemyCount;
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::InvalidState);
  assert(!edges.previous.fire && mag.rounds==3);
  cursor.target=0;
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false}).status==
         ArmControlStatus::Applied);
  assert(mag.rounds==2);
}

void burst_new_zr_edge_costs_two_ammo_and_never_repeats_held() {
  auto b=make_demo_battle();ArmMagazine mag{};BattleCursor cursor{};
  ArmEdgeState edges{};
  const auto first=advance_arm_controller(b,mag,cursor,edges,{false,false,true});
  assert(first.status==ArmControlStatus::Applied);
  assert(first.update.battle.inflicted==14);
  assert(b.enemies[0].hp==0 && mag.rounds==1);
  assert(cursor.actor==1 && cursor.target==1);
  for(int i=0;i<5;++i)
    assert(advance_arm_controller(b,mag,cursor,edges,
                                 {false,false,true}).status==ArmControlStatus::Idle);
  assert(mag.rounds==1 && b.enemies[1].hp==17);
}

void simultaneous_burst_and_fire_consumes_both_physical_edges() {
  auto b=make_demo_battle();ArmMagazine mag{};BattleCursor cursor{};
  ArmEdgeState edges{};
  auto r=advance_arm_controller(b,mag,cursor,edges,{true,false,true});
  assert(r.status==ArmControlStatus::Idle && mag.rounds==3);
  assert(advance_arm_controller(b,mag,cursor,edges,
                                {false,false,true}).status==ArmControlStatus::Idle);
  assert(b.enemies[0].hp==14);
  release(b,mag,cursor,edges);
  r=advance_arm_controller(b,mag,cursor,edges,{false,false,true});
  assert(r.status==ArmControlStatus::Applied && mag.rounds==1);
}

void insufficient_ammo_burst_refused_without_consuming_actor_turn() {
  auto b=make_demo_battle();ArmMagazine mag{1,3,10};
  BattleCursor cursor{};ArmEdgeState edges{};
  const auto r=advance_arm_controller(b,mag,cursor,edges,{false,false,true});
  assert(r.status==ArmControlStatus::Refused);
  assert(r.update.step==ArmStep::InsufficientAmmo);
  assert(b.enemies[0].hp==14 && mag.rounds==1);
  assert(!b.acted[0] && cursor.actor==0 && edges.previous.burst);
  release(b,mag,cursor,edges);
  assert(advance_arm_controller(b,mag,cursor,edges,{true,false,false}).status==
         ArmControlStatus::Applied);
  assert(mag.rounds==0 && b.enemies[0].hp==5);
}

} // namespace

int main() {
  held_fire_cannot_repeat_or_attack_next_actor();
  simultaneous_fire_and_reload_never_fires_on_release();
  reload_uses_normal_turn_and_never_grants_guard();
  stale_dead_target_is_repaired_only_on_successful_fire();
  rejected_empty_magazine_leaves_cursor_battle_and_melee_untouched();
  corrupt_state_does_not_consume_fire_edge_or_ammo();
  burst_new_zr_edge_costs_two_ammo_and_never_repeats_held();
  simultaneous_burst_and_fire_consumes_both_physical_edges();
  insufficient_ammo_burst_refused_without_consuming_actor_turn();
}
