#include "field_battle_controller.hpp"
#include <cassert>
#include <cstddef>

using namespace wa::field;
namespace {
BattleControlFrame press(FieldBattle& battle, BattleCursor& cursor,
                         BattlePad sample) {
  return advance_battle_controller(battle, cursor, sample);
}
void release(FieldBattle& battle, BattleCursor& cursor) {
  assert(press(battle,cursor,{}).status == BattleControlStatus::Idle);
}
void repeated_confirm_does_not_double_attack() {
  auto b=make_demo_battle(); BattleCursor c{};
  BattlePad a{}; a.confirm=true;
  auto r=press(b,c,a);
  assert(r.status==BattleControlStatus::ActionApplied && r.action.inflicted==6);
  assert(c.actor==1 && b.enemies[0].hp==8);
  r=press(b,c,a);
  assert(r.status==BattleControlStatus::Idle && b.enemies[0].hp==8);
  release(b,c);
  r=press(b,c,a);
  assert(r.status==BattleControlStatus::ActionApplied && r.action.inflicted==5);
  assert(c.actor==2 && b.enemies[0].hp==3);
}
void actor_and_target_cursor_skip_ineligible() {
  auto b=make_demo_battle(); BattleCursor c{};
  b.party[1].hp=0;
  BattlePad right{}; right.right=true;
  assert(press(b,c,right).status==BattleControlStatus::CursorMoved);
  assert(c.actor==2);
  assert(press(b,c,right).status==BattleControlStatus::Idle && c.actor==2);
  release(b,c);
  assert(press(b,c,right).status==BattleControlStatus::CursorMoved && c.actor==0);
  release(b,c);
  BattlePad up{}; up.up=true;
  assert(press(b,c,up).status==BattleControlStatus::CursorMoved && c.target==1);
  release(b,c);
  b.enemies[1].hp=0;
  assert(press(b,c,{}).status==BattleControlStatus::Idle && c.target==0);
  BattlePad down{}; down.down=true;
  assert(press(b,c,down).status==BattleControlStatus::Idle && c.target==0);
}
void navigation_and_conflicting_inputs_are_safe() {
  auto b=make_demo_battle(); BattleCursor c{};
  BattlePad both{}; both.confirm=true; both.guard=true;
  assert(press(b,c,both).status==BattleControlStatus::Idle);
  assert(b.enemies[0].hp==14 && !b.acted[0]);
  release(b,c);
  BattlePad mixed{}; mixed.right=true; mixed.confirm=true;
  assert(press(b,c,mixed).status==BattleControlStatus::CursorMoved);
  assert(c.actor==1 && b.enemies[0].hp==14);
  assert(press(b,c,{}).status==BattleControlStatus::Idle);
  BattlePad rightleft{}; rightleft.left=true; rightleft.right=true;
  assert(press(b,c,rightleft).status==BattleControlStatus::Idle && c.actor==1);
}
void defending_round_and_result() {
  auto b=make_demo_battle(); BattleCursor c{};
  BattlePad y{}; y.guard=true;
  assert(press(b,c,y).status==BattleControlStatus::ActionApplied);
  release(b,c);
  assert(press(b,c,y).status==BattleControlStatus::ActionApplied);
  release(b,c);
  const auto result=press(b,c,y);
  assert(result.status==BattleControlStatus::ActionApplied);
  assert(result.action.enemy_turn_completed && b.round==2);
  assert(b.party[0].hp==22 && b.party[1].hp==17 && b.party[2].hp==18);
  assert(c.actor==0 && c.target==0);
  release(b,c);
  assert(press(b,c,y).status==BattleControlStatus::ActionApplied);
  assert(b.acted[0]);
}
void one_final_target_and_finished_battle() {
  auto b=make_demo_battle(); BattleCursor c{};
  b.enemies[1].hp=0;
  b.enemies[0].hp=1;
  c.target=1; // Stale selection is repaired before consuming A.
  BattlePad a{}; a.confirm=true;
  const auto r=press(b,c,a);
  assert(r.status==BattleControlStatus::ActionApplied);
  assert(r.action.phase==BattlePhase::Victory && !r.action.enemy_turn_completed);
  assert(c.target==0);
  assert(b.phase==BattlePhase::Victory);
  const auto snapshot=b;
  release(b,c);
  assert(press(b,c,a).status==BattleControlStatus::Idle);
  assert(b.enemies[0].hp==snapshot.enemies[0].hp);
}
void corruption_rejected_without_input_latch_mutation() {
  auto b=make_demo_battle(); BattleCursor c{};
  c.actor=kBattlePartySize;
  BattlePad a{}; a.confirm=true;
  assert(press(b,c,a).status==BattleControlStatus::InvalidState);
  assert(!c.previous.confirm && b.enemies[0].hp==14);
  c.actor=0; b.party[0].hp=999;
  assert(press(b,c,a).status==BattleControlStatus::InvalidState);
  assert(!c.previous.confirm && b.enemies[0].hp==14);
}
} // namespace
int main() {
  repeated_confirm_does_not_double_attack();
  actor_and_target_cursor_skip_ineligible();
  navigation_and_conflicting_inputs_are_safe();
  defending_round_and_result();
  one_final_target_and_finished_battle();
  corruption_rejected_without_input_latch_mutation();
}
