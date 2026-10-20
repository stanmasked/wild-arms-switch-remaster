// Stage 348: in-game synthetic battle feedback uses real applied results.
#include "field_battle_session.hpp"

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

using namespace wa::field;
namespace {
constexpr std::uint32_t canary=0xC0DEF00Du;
constexpr int stride=kRasterWidth+8;
struct Frame {
  std::vector<std::uint32_t> buffer=std::vector<std::uint32_t>(
      static_cast<std::size_t>(stride)*kRasterHeight+16,canary);
  PixelTarget target{buffer.data(),kRasterWidth,kRasterHeight,stride};
  std::uint32_t pixel(int x,int y) const {
    return buffer[static_cast<std::size_t>(y)*stride+x];
  }
  void guards() const {
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<stride;++x)assert(pixel(x,y)==canary);
    for(std::size_t i=static_cast<std::size_t>(stride)*kRasterHeight;i<buffer.size();++i)
      assert(buffer[i]==canary);
  }
};
void test_feedback_computation_and_rejection() {
  const auto empty=battle_feedback_from_action(
      BattleMove::Strike, BattleUpdate{});
  assert(empty.kind==BattleFeedbackKind::None);
  assert(valid_battle_feedback(empty));
  assert(!valid_battle_feedback({BattleFeedbackKind::Strike,0,0,false}));
  assert(!valid_battle_feedback({BattleFeedbackKind::Guard,1,0,false}));
  assert(!valid_battle_feedback({BattleFeedbackKind::None,1,0,false}));
  assert(!valid_battle_feedback({static_cast<BattleFeedbackKind>(99),0,0,false}));
  BattleUpdate u{};
  u.step=BattleStep::Applied;
  u.inflicted=6;
  auto strike=battle_feedback_from_action(BattleMove::Strike,u);
  assert(strike.kind==BattleFeedbackKind::Strike &&
         strike.damage==6 && valid_battle_feedback(strike));
  u.inflicted=0;
  auto guard=battle_feedback_from_action(BattleMove::Guard,u);
  assert(guard.kind==BattleFeedbackKind::Guard &&
         guard.damage==0 && valid_battle_feedback(guard));
  u.enemy_turn_completed=true;
  u.retaliation={2,3,0};
  guard=battle_feedback_from_action(BattleMove::Guard,u);
  assert(guard.enemy_damage==5 && guard.enemy_turn_completed);
  assert(valid_battle_feedback(guard));
}
void test_strike_text_hold_and_guard_text() {
  Frame f;
  FieldBattleSession session{};
  FieldBattleSessionInput start{};
  start.open=true;start.manual_mode=true;
  auto step=advance_battle_session(session,start,f.target);
  assert(step.entered && step.status==BattleSceneStatus::Rendered);
  const auto footer=rgba(28,40,57);
  assert(f.pixel(72,682)==footer && session.last_feedback.kind==BattleFeedbackKind::None);
  FieldBattleSessionInput attack{};
  attack.pad.confirm=true;
  step=advance_battle_session(session,attack,f.target);
  assert(step.control.status==BattleControlStatus::ActionApplied);
  assert(session.last_feedback.kind==BattleFeedbackKind::Strike);
  assert(session.last_feedback.damage==6);
  assert(f.pixel(72,682)==kBattleGold);
  const auto attack_image=f.buffer;
  const auto held=advance_battle_session(session,attack,f.target);
  assert(held.control.status==BattleControlStatus::Idle);
  assert(f.buffer==attack_image);
  assert(session.last_feedback.damage==6);
  attack.pad={};
  (void)advance_battle_session(session,attack,f.target);
  assert(f.buffer==attack_image); // Last action is persistent.
  attack.pad.guard=true;
  const auto defended=advance_battle_session(session,attack,f.target);
  assert(defended.control.status==BattleControlStatus::ActionApplied);
  assert(session.last_feedback.kind==BattleFeedbackKind::Guard);
  assert(session.last_feedback.damage==0);
  assert(f.pixel(72,682)==kBattleBlue);
  f.guards();
}
void test_actual_enemy_reply_and_reset() {
  Frame f;FieldBattleSession session{};
  FieldBattleSessionInput open{};
  open.manual_mode=true;open.open=true;
  assert(advance_battle_session(session,open,f.target).entered);
  FieldBattleSessionInput input{};
  input.pad.guard=true;
  assert(advance_battle_session(session,input,f.target).control.status==
         BattleControlStatus::ActionApplied);
  input.pad={};
  (void)advance_battle_session(session,input,f.target);
  input.pad.guard=true;
  assert(advance_battle_session(session,input,f.target).control.status==
         BattleControlStatus::ActionApplied);
  input.pad={};
  (void)advance_battle_session(session,input,f.target);
  input.pad.guard=true;
  const auto third=advance_battle_session(session,input,f.target);
  assert(third.control.status==BattleControlStatus::ActionApplied);
  assert(third.control.action.enemy_turn_completed);
  assert(session.last_feedback.kind==BattleFeedbackKind::Guard);
  assert(session.last_feedback.enemy_turn_completed);
  assert(session.last_feedback.enemy_damage==5);
  assert(session.battle.round==2);
  assert(f.pixel(72,682)==kBattleBlue);
  input.pad={};input.close=true;
  const auto before=f.buffer;
  assert(advance_battle_session(session,input,f.target).exited);
  assert(f.buffer==before); // B cannot paint on the field.
  assert(advance_battle_session(session,open,f.target).entered);
  assert(session.last_feedback.kind==BattleFeedbackKind::None);
  assert(f.pixel(72,682)==rgba(28,40,57));
  f.guards();
}
void test_corrupt_feedback_atomic() {
  Frame f;FieldBattleSession session{};
  FieldBattleSessionInput open{};
  open.manual_mode=true;open.open=true;
  assert(advance_battle_session(session,open,f.target).entered);
  session.last_feedback.kind=static_cast<BattleFeedbackKind>(99);
  const auto before=f.buffer;
  FieldBattleSessionInput attack{};attack.pad.confirm=true;
  const auto r=advance_battle_session(session,attack,f.target);
  assert(r.status==BattleSceneStatus::InvalidBattle);
  assert(!session.cursor.previous.confirm);
  assert(session.last_feedback.kind==static_cast<BattleFeedbackKind>(99));
  assert(f.buffer==before);
  f.guards();
}
}
int main(){
  test_feedback_computation_and_rejection();
  test_strike_text_hold_and_guard_text();
  test_actual_enemy_reply_and_reset();
  test_corrupt_feedback_atomic();
}
