// Stage 357: real session-close reward integration; independent of PS1 data.
#include "field_battle_session.hpp"
#include "field_runtime.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

using namespace wa::field;
namespace {
struct Frame {
  static constexpr int kStride=kRasterWidth+8;
  static constexpr std::uint32_t kCanary=0xA6B7C8D9u;
  std::vector<std::uint32_t> data=std::vector<std::uint32_t>(
      static_cast<std::size_t>(kStride)*kRasterHeight+16,kCanary);
  PixelTarget pixels{data.data(),kRasterWidth,kRasterHeight,kStride};
  std::uint32_t at(int x,int y) const {
    return data[static_cast<std::size_t>(y)*kStride+x];
  }
  void canaries() const {
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<kStride;++x)
        assert(at(x,y)==kCanary);
    for(std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
        i<data.size();++i) assert(data[i]==kCanary);
  }
};
FieldBattleSessionInput open() {FieldBattleSessionInput i{};i.open=true;i.manual_mode=true;return i;}
FieldBattleSessionInput strike() {FieldBattleSessionInput i{};i.pad.confirm=true;return i;}
FieldBattleSessionInput close() {FieldBattleSessionInput i{};i.close=true;return i;}

void finish_two_weak_foes(FieldBattleSession& s,Frame& f) {
  assert(advance_battle_session(s,open(),f.pixels).entered);
  s.battle.enemies[0].hp=1;
  s.battle.enemies[1].hp=1;
  assert(advance_battle_session(s,strike(),f.pixels).control.status==
         BattleControlStatus::ActionApplied);
  assert(advance_battle_session(s,{},f.pixels).status==
         BattleSceneStatus::Rendered);
  assert(advance_battle_session(s,strike(),f.pixels).control.status==
         BattleControlStatus::ActionApplied);
  assert(s.battle.phase==BattlePhase::Victory);
}
void test_no_reward_until_confirmed_victory_and_exactly_once() {
  FieldBattleSession s{};Frame f;
  finish_two_weak_foes(s,f);
  assert(s.rewards.experience==0 && s.rewards.gella==0);
  assert(s.history.victories==0);
  const auto closed=advance_battle_session(s,close(),f.pixels);
  assert(closed.exited && closed.resolution==BattleResolution::Victory);
  assert(closed.payout.experience==kPrototypeVictoryExp &&
         closed.payout.gella==kPrototypeVictoryGella);
  assert(s.history.victories==1);
  assert(s.rewards.experience==kPrototypeVictoryExp);
  assert(s.rewards.gella==kPrototypeVictoryGella);
  const auto repeated=advance_battle_session(s,close(),f.pixels);
  assert(repeated.payout.experience==0 && repeated.payout.gella==0);
  assert(!repeated.exited);
  assert(s.rewards.experience==kPrototypeVictoryExp);
  f.canaries();
}
void test_two_independent_wins_are_cumulative() {
  FieldBattleSession s{};Frame f;
  for (int fight=0;fight<2;++fight) {
    finish_two_weak_foes(s,f);
    const auto done=advance_battle_session(s,close(),f.pixels);
    assert(done.payout.experience==kPrototypeVictoryExp);
    assert(done.payout.gella==kPrototypeVictoryGella);
  }
  assert(s.rewards.experience==2*kPrototypeVictoryExp);
  assert(s.rewards.gella==2*kPrototypeVictoryGella);
  assert(s.history.victories==2);
  f.canaries();
}
void test_retreat_and_defeat_cannot_earn_rewards() {
  FieldBattleSession s{};Frame f;
  assert(advance_battle_session(s,open(),f.pixels).entered);
  const auto quit=advance_battle_session(s,close(),f.pixels);
  assert(quit.resolution==BattleResolution::Retreat);
  assert(quit.payout.experience==0 && quit.payout.gella==0);
  assert(s.rewards.experience==0 && s.rewards.gella==0);
  assert(advance_battle_session(s,open(),f.pixels).entered);
  s.battle.party[0].hp=0;
  s.battle.party[1].hp=0;
  s.battle.party[2].hp=1;
  FieldBattleSessionInput defend{};defend.pad.guard=true;
  assert(advance_battle_session(s,defend,f.pixels).control.status==
         BattleControlStatus::ActionApplied);
  assert(s.battle.phase==BattlePhase::Defeat);
  const auto lost=advance_battle_session(s,close(),f.pixels);
  assert(lost.resolution==BattleResolution::Defeat);
  assert(lost.payout.experience==0 && lost.payout.gella==0);
  assert(s.rewards.experience==0 && s.rewards.gella==0);
  assert(s.history.retreats==1 && s.history.defeats==1);
  f.canaries();
}
void test_saturation_reports_actual_delta_no_rollover() {
  FieldBattleSession s{};Frame f;
  s.rewards.experience=std::numeric_limits<std::uint32_t>::max()-3;
  s.rewards.gella=std::numeric_limits<std::uint32_t>::max()-5;
  finish_two_weak_foes(s,f);
  const auto paid=advance_battle_session(s,close(),f.pixels).payout;
  assert(paid.experience==3 && paid.gella==5);
  assert(s.rewards.experience==std::numeric_limits<std::uint32_t>::max());
  assert(s.rewards.gella==std::numeric_limits<std::uint32_t>::max());
  finish_two_weak_foes(s,f);
  const auto second=advance_battle_session(s,close(),f.pixels).payout;
  assert(second.experience==0 && second.gella==0);
  f.canaries();
}
void test_invalid_state_is_atomic_and_field_save_untouched() {
  FieldBattleSession s{};Frame f;
  const auto world=make_demo_world();
  auto runtime=start_field_runtime(world,19200000ULL,0);
  assert(advance_field_runtime(world,runtime,0,{},f.pixels).status==
         RuntimeStatus::Rendered);
  const auto original=f.data;
  assert(advance_battle_session(s,open(),f.pixels).entered);
  s.battle.party[0].hp=25; // Invalid battle, cannot close or grant EXP.
  const auto before=s.rewards;
  auto failed=advance_battle_session(s,close(),f.pixels);
  assert(failed.status==BattleSceneStatus::InvalidBattle);
  assert(!failed.exited && failed.payout.experience==0);
  assert(s.rewards.experience==before.experience && s.rewards.gella==before.gella);
  s.battle=make_demo_battle();
  auto quit=advance_battle_session(s,close(),f.pixels);
  assert(quit.resolution==BattleResolution::Retreat);
  assert(advance_field_runtime(world,runtime,320000,{},f.pixels).status==
         RuntimeStatus::Rendered);
  assert(f.data==original);
  assert(!runtime.quicksave.occupied && runtime.discoveries.count==0);
  f.canaries();
}
void test_opt_in_balance_draw_never_changes_game_state() {
  Frame f;FieldBattleSession s{};
  const auto world=make_demo_world();
  auto rt=start_field_runtime(world,19200000ULL,0);
  assert(advance_field_runtime(world,rt,0,{},f.pixels).status==
         RuntimeStatus::Rendered);
  const auto baseline=f.data;
  assert(draw_field_battle_history(f.pixels,s.history));
  draw_battle_reward_balance(f.pixels,s.rewards);
  assert(f.data!=baseline);
  assert(rt.manual.player.x==1 && rt.manual.player.y==1);
  assert(!rt.quicksave.occupied && rt.discoveries.count==0);
  assert(advance_field_runtime(world,rt,320000,{},f.pixels).status==
         RuntimeStatus::Rendered);
  assert(f.data==baseline);
  f.canaries();
}
}
int main() {
 test_no_reward_until_confirmed_victory_and_exactly_once();
 test_two_independent_wins_are_cumulative();
 test_retreat_and_defeat_cannot_earn_rewards();
 test_saturation_reports_actual_delta_no_rollover();
 test_invalid_state_is_atomic_and_field_save_untouched();
 test_opt_in_balance_draw_never_changes_game_state();
}
