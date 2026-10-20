// Stage 344: field and battle sharing a real host framebuffer.
// Replay the Switch main loop's neutral-pad ownership contract, not a mock
// world. This preserves the established exploratory controller pipeline.
#include "field_runtime.hpp"
#include "field_battle_session.hpp"

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace {
using namespace wa::field;
constexpr std::uint64_t kFreq = 19200000;
constexpr std::uint64_t kStep = 320000;
constexpr std::uint32_t kGuard = 0xC0FFEE11u;
constexpr int kStride = kRasterWidth + 8;
struct Screen {
  std::vector<std::uint32_t> buffer = std::vector<std::uint32_t>(
      static_cast<std::size_t>(kStride)*kRasterHeight + 32, kGuard);
  PixelTarget target{buffer.data(),kRasterWidth,kRasterHeight,kStride};
  void guards() const {
    for (int row=0;row<kRasterHeight;++row)
      for (int x=kRasterWidth;x<kStride;++x)
        assert(buffer[static_cast<std::size_t>(row)*kStride+x]==kGuard);
    for (std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
         i<buffer.size();++i) assert(buffer[i]==kGuard);
  }
};
struct Replay {
  FieldWorld world = make_demo_world();
  FieldRuntime field = start_field_runtime(world,kFreq,0);
  FieldBattleSession battle{};
  Screen display{};
  std::uint64_t tick=0;

  BattleSceneFrame step(bool open=false,bool close=false,BattlePad pad={}) {
    // Exactly as Switch main: battle buttons never enter the exploration
    // simulation; the shared timer still advances every frame.
    const auto field_output = advance_field_runtime(
        world,field,tick+=kStep,RuntimeControls{},display.target);
    assert(field_output.status==RuntimeStatus::Rendered);
    const FieldBattleSessionInput input{
        open,close,!field.autoplay,pad};
    const auto combat = advance_battle_session(battle,input,display.target);
    assert(combat.status==BattleSceneStatus::Rendered ||
           combat.status==BattleSceneStatus::Inactive);
    display.guards();
    return combat;
  }

  void assert_stable_world() const {
    assert(!field.autoplay && field.manual.area==0);
    assert(field.manual.player.x==1 && field.manual.player.y==1);
    assert(field.manual.player.successful_moves==0);
    assert(field.manual.pending==Trigger::None);
    assert(!field.quicksave.occupied);
    assert(field.discoveries.count==0);
  }
};

void test_battle_actions_own_input_and_field_pixels_restore_exactly() {
  Replay p;
  assert(p.world.valid());
  p.step();
  p.assert_stable_world();
  const auto original=p.display.buffer;

  // On entry, R+A and Y mean battle ownership. They may not change the
  // field map, quicksave slot, or pending trigger state.
  BattlePad start{};
  start.confirm=true;
  start.guard=true;
  auto entering=p.step(true,false,start);
  assert(entering.entered && p.battle.active);
  assert(p.battle.battle.enemies[0].hp==14);
  p.assert_stable_world();
  assert(p.display.buffer!=original);

  // Holding A from the opening frame must not cause another action.
  BattlePad held{};
  held.confirm=true;
  assert(p.step(false,false,held).control.status==BattleControlStatus::Idle);
  assert(p.battle.battle.enemies[0].hp==14);
  p.assert_stable_world();
  p.step();  // Release A.
  auto strike=p.step(false,false,held);
  assert(strike.control.status==BattleControlStatus::ActionApplied);
  assert(strike.control.action.inflicted==6);
  assert(p.battle.battle.enemies[0].hp==8);
  p.assert_stable_world();
  const auto strike_frame=p.display.buffer;
  assert(p.step(false,false,held).control.status==BattleControlStatus::Idle);
  assert(strike_frame==p.display.buffer);

  // Physical Switch Y in battle defends, never calls field quicksave.
  p.step();  // Release A.
  BattlePad defend{}; defend.guard=true;
  auto guarded=p.step(false,false,defend);
  assert(guarded.control.status==BattleControlStatus::ActionApplied);
  assert(p.battle.battle.guarding[1]);
  assert(p.battle.cursor.actor==2);
  p.assert_stable_world();

  // On the closing B frame, the field renderer already produced its
  // normal pixels and battle_close is forbidden to overlay anything.
  auto left=p.step(false,true);
  assert(left.exited && !p.battle.active);
  p.assert_stable_world();
  assert(p.display.buffer==original);
  p.display.guards();

  // The reopened synthetic fight is fresh and the world is still frozen.
  assert(p.step(true).entered);
  assert(p.battle.battle.enemies[0].hp==14);
  assert(!p.battle.battle.acted[0]);
  assert(p.step(false,true).exited);
  assert(p.display.buffer==original);
}

void test_prior_clue_and_real_quicksave_survive_combat_overlay() {
  Replay p;
  p.step();
  // Seed a genuinely valid, preexisting session clue and RAM snapshot.
  // Unlike the empty-map fixture, the returned pixels now include the
  // distinctive discovered-clue marker.
  assert(record_discovery(p.world, p.field.discoveries, 0, 4, 1) ==
         DiscoveryResult::Recorded);
  assert(valid_discovery_journal(p.world, p.field.discoveries));
  assert(save_field_snapshot(p.world, p.field.manual, p.field.quicksave) ==
         SnapshotOutcome::Stored);
  assert(p.field.quicksave.occupied);
  const WorldState saved = p.field.quicksave.world;
  p.step();
  const auto rendered_clue_field = p.display.buffer;

  assert(p.step(true).entered);
  assert(p.battle.active);
  // The new battle is free to change its own combat stats only.
  BattlePad strike{}; strike.confirm=true;
  const auto attacked=p.step(false,false,strike);
  assert(attacked.control.status==BattleControlStatus::ActionApplied);
  assert(p.battle.battle.enemies[0].hp==8);
  p.step(); // A released.
  BattlePad defend{}; defend.guard=true;
  const auto guarded=p.step(false,false,defend);
  assert(guarded.control.status==BattleControlStatus::ActionApplied);
  assert(p.battle.battle.guarding[1]);
  assert(p.field.discoveries.count==1);
  assert(has_discovered_clue(p.field.discoveries,0,4,1));
  assert(p.field.quicksave.occupied);
  assert(p.field.quicksave.world.area==saved.area);
  assert(p.field.quicksave.world.player.x==saved.player.x);
  assert(p.field.quicksave.world.player.y==saved.player.y);
  assert(p.field.quicksave.world.player.successful_moves==
         saved.player.successful_moves);
  assert(p.field.quicksave.world.pending==saved.pending);
  assert(p.field.quicksave.world.decoder.confirm_down==
         saved.decoder.confirm_down);

  assert(p.step(false,true).exited);
  assert(!p.battle.active);
  assert(p.display.buffer==rendered_clue_field);
  assert(p.field.discoveries.count==1);
  assert(valid_discovery_journal(p.world,p.field.discoveries));
  assert(p.field.quicksave.occupied);
  // A battle return must not replace the player's original quicksave.
  WorldState recovered{};
  assert(load_field_snapshot(
      p.world,p.field.quicksave,recovered)==SnapshotOutcome::Restored);
  assert(recovered.area==saved.area && recovered.player.x==saved.player.x &&
         recovered.player.y==saved.player.y &&
         recovered.pending==saved.pending);
  p.display.guards();
}

void test_exploration_resumes_from_same_tile_after_battle() {
  Replay p;
  p.step();
  p.step(true);
  BattlePad guard{};guard.guard=true;
  assert(p.step(false,false,guard).control.status==
         BattleControlStatus::ActionApplied);
  assert(p.step(false,true).exited);
  p.assert_stable_world();
  // Real controller D-pad on the following field frame still moves.
  const RuntimeControls right{PadSample{.dpad_right=true}};
  auto frame=advance_field_runtime(
      p.world,p.field,p.tick+ kFreq*160/1000,right,p.display.target);
  assert(frame.status==RuntimeStatus::Rendered);
  assert(p.field.manual.player.x==2 && p.field.manual.player.y==1);
  assert(p.field.manual.player.successful_moves==1);
  assert(!p.field.quicksave.occupied);
  p.display.guards();
}
}
int main(){
  test_battle_actions_own_input_and_field_pixels_restore_exactly();
  test_exploration_resumes_from_same_tile_after_battle();
  test_prior_clue_and_real_quicksave_survive_combat_overlay();
}
