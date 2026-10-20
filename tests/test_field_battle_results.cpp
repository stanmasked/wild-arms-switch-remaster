// Stage 355: real battle-controller result transitions, not fake counters.
#include "field_battle_session.hpp"
#include "field_runtime.hpp"

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

using namespace wa::field;
namespace {
constexpr int kStride = kRasterWidth + 8;
constexpr std::uint32_t kCanary = 0xCAFE9876u;
struct Screen {
  std::vector<std::uint32_t> data = std::vector<std::uint32_t>(
    static_cast<std::size_t>(kStride) * kRasterHeight + 32, kCanary);
  PixelTarget target{data.data(),kRasterWidth,kRasterHeight,kStride};
  std::uint32_t at(int x,int y) const {
    return data[static_cast<std::size_t>(y)*kStride+x];
  }
  void guards() const {
    for (int y=0;y<kRasterHeight;++y)
      for (int x=kRasterWidth;x<kStride;++x)
        assert(at(x,y)==kCanary);
    for (std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
         i<data.size();++i) assert(data[i]==kCanary);
  }
};
FieldBattleSessionInput open_button() {
  FieldBattleSessionInput input{};
  input.open=true;
  input.manual_mode=true;
  return input;
}
FieldBattleSessionInput strike_button() {
  FieldBattleSessionInput input{};
  input.pad.confirm=true;
  return input;
}
FieldBattleSessionInput guard_button() {
  FieldBattleSessionInput input{};
  input.pad.guard=true;
  return input;
}
FieldBattleSessionInput close_button() {
  FieldBattleSessionInput input{};
  input.close=true;
  return input;
}
void test_first_early_exit_and_no_double_b() {
  Screen f;
  FieldBattleSession s{};
  const auto base=s.history;
  assert(s.history.last==BattleResolution::None);
  assert(advance_battle_session(s,open_button(),f.target).entered);
  const auto first=f.data;
  assert(advance_battle_session(s,close_button(),f.target).resolution==
         BattleResolution::Retreat);
  assert(!s.active);
  assert(s.history.retreats==base.retreats+1);
  assert(s.history.last==BattleResolution::Retreat);
  assert(f.data==first); // Closing never overwrites a pixel itself.
  const auto after=advance_battle_session(s,close_button(),f.target);
  assert(!after.exited && after.resolution==BattleResolution::None);
  assert(s.history.retreats==1);

  // New battle reset is independent of the ledger. Previous results
  // are shown only on a subsequent combat screen.
  assert(advance_battle_session(s,open_button(),f.target).entered);
  assert(s.battle.enemies[0].hp==14 && s.battle.round==1);
  assert(s.history.retreats==1);
  assert(f.data!=first);
  f.guards();
}
void test_real_controller_victory_counted_once() {
  Screen f;
  FieldBattleSession s{};
  assert(advance_battle_session(s,open_button(),f.target).entered);
  s.battle.enemies[0].hp=1;
  s.battle.enemies[1].hp=1;
  auto first=advance_battle_session(s,strike_button(),f.target);
  assert(first.control.status==BattleControlStatus::ActionApplied);
  assert(first.control.action.inflicted==1);
  assert(s.battle.enemies[0].hp==0);
  assert(advance_battle_session(s,{},f.target).status==
         BattleSceneStatus::Rendered);
  const auto last=advance_battle_session(s,strike_button(),f.target);
  assert(last.control.status==BattleControlStatus::ActionApplied);
  assert(s.battle.phase==BattlePhase::Victory);
  assert(f.at(320,294)==kBattleGreen);
  assert(s.history.victories==0); // Not counted before B confirmation.
  assert(advance_battle_session(s,strike_button(),f.target).control.status==
         BattleControlStatus::Idle);
  const auto result=advance_battle_session(s,close_button(),f.target);
  assert(result.exited && result.resolution==BattleResolution::Victory);
  assert(s.history.victories==1 && s.history.defeats==0 &&
         s.history.retreats==0);
  assert(s.history.last==BattleResolution::Victory);
  assert(advance_battle_session(s,close_button(),f.target).status==
         BattleSceneStatus::Inactive);
  assert(s.history.victories==1);
  f.guards();
}
void test_real_retaliation_defeat_counts_loss() {
  Screen f;
  FieldBattleSession s{};
  assert(advance_battle_session(s,open_button(),f.target).entered);
  // Valid last-hero-standing condition: final guard completes the
  // player turn, real enemy retaliation defeats that last hero.
  s.battle.party[0].hp=0;
  s.battle.party[1].hp=0;
  s.battle.party[2].hp=1;
  assert(valid_field_battle(s.battle));
  const auto attack=advance_battle_session(s,guard_button(),f.target);
  assert(attack.control.status==BattleControlStatus::ActionApplied);
  assert(attack.control.action.enemy_turn_completed);
  assert(s.battle.phase==BattlePhase::Defeat);
  assert(s.battle.party[2].hp==0);
  assert(f.at(320,294)==kBattleRed);
  assert(s.history.defeats==0);
  const auto closed=advance_battle_session(s,close_button(),f.target);
  assert(closed.exited && closed.resolution==BattleResolution::Defeat);
  assert(s.history.defeats==1 && s.history.last==BattleResolution::Defeat);
  f.guards();
}
void test_saturating_counts_and_reopen_preserves_record() {
  Screen f;
  FieldBattleSession s{};
  s.history.victories=std::numeric_limits<std::uint32_t>::max();
  assert(advance_battle_session(s,open_button(),f.target).entered);
  s.battle.enemies[0].hp=0;
  s.battle.enemies[1].hp=0;
  s.battle.phase=BattlePhase::Victory;
  assert(valid_field_battle(s.battle));
  assert(advance_battle_session(s,close_button(),f.target).resolution==
         BattleResolution::Victory);
  assert(s.history.victories==std::numeric_limits<std::uint32_t>::max());
  assert(s.history.last==BattleResolution::Victory);
  assert(advance_battle_session(s,open_button(),f.target).entered);
  assert(s.battle.phase==BattlePhase::Player);
  assert(s.history.victories==std::numeric_limits<std::uint32_t>::max());
  assert(advance_battle_session(s,close_button(),f.target).resolution==
         BattleResolution::Retreat);
  assert(s.history.retreats==1);
  f.guards();
}
void test_battle_results_field_hud_explicit_only_and_no_save_changes() {
  const auto world=make_demo_world();
  auto field=start_field_runtime(world,19200000ULL,0);
  Screen f;
  FieldBattleSession s{};
  assert(advance_field_runtime(world,field,0,{},f.target).status==
         RuntimeStatus::Rendered);
  const auto field_pixels=f.data;
  assert(advance_battle_session(s,open_button(),f.target).entered);
  assert(advance_battle_session(s,close_button(),f.target).exited);
  assert(s.history.retreats==1);
  assert(!field.quicksave.occupied && field.discoveries.count==0);
  // Switch main always draws the real field FIRST on the B-close frame.
  assert(advance_field_runtime(world,field,320000,{},f.target).status==
         RuntimeStatus::Rendered);
  assert(f.data==field_pixels);
  // ZL is the only trigger to render this read-only nonpersistent panel.
  assert(draw_field_battle_history(f.target,s.history));
  assert(f.data!=field_pixels && f.at(690,612)==kBattleGold);
  assert(!field.quicksave.occupied && field.discoveries.count==0);
  assert(field.manual.player.x==1 && field.manual.player.y==1);
  // Subsequent non-ZL frame is back to fully identical vanilla field.
  assert(advance_field_runtime(world,field,640000,{},f.target).status==
         RuntimeStatus::Rendered);
  assert(f.data==field_pixels);
  f.guards();
}
void test_invalid_target_refuses_history_draw_and_exit_is_atomic() {
  Screen f;
  FieldBattleSession s{};
  auto bad=f.target;bad.width=kRasterWidth-1;
  const auto pixels=f.data;
  assert(!draw_field_battle_history(bad,s.history));
  assert(f.data==pixels);
  assert(advance_battle_session(s,open_button(),bad).status==
         BattleSceneStatus::InvalidTarget);
  assert(!s.active && s.history.last==BattleResolution::None);
  assert(advance_battle_session(s,open_button(),f.target).entered);
  s.battle.party[0].hp=25; // Invalid fighter state.
  const auto record_before=s.history;
  const auto failing=advance_battle_session(s,close_button(),f.target);
  assert(failing.status==BattleSceneStatus::InvalidBattle);
  assert(!failing.exited && s.active);
  assert(s.history.last==record_before.last);
  assert(s.history.retreats==record_before.retreats);
  assert(s.history.victories==record_before.victories);
  assert(s.history.defeats==record_before.defeats);
  f.guards();
}
}
int main() {
  test_first_early_exit_and_no_double_b();
  test_real_controller_victory_counted_once();
  test_real_retaliation_defeat_counts_loss();
  test_saturating_counts_and_reopen_preserves_record();
  test_battle_results_field_hud_explicit_only_and_no_save_changes();
  test_invalid_target_refuses_history_draw_and_exit_is_atomic();
}
