#include "field_encounters.hpp"
#include "field_runtime.hpp"
#include "field_battle_session.hpp"
#include <cassert>
#include <cstdint>
#include <vector>

using namespace wa::field;
namespace {

EncounterFrame run(EncounterDirector& d, WorldState& w,
                   EncounterControls c={}) {
  return advance_field_encounters(d,w,c);
}

void test_disabled_is_inert_and_toggle_has_no_immediate_encounter() {
  WorldState w{};EncounterDirector d{};
  assert(!run(d,w).triggered && !d.enabled);
  for(unsigned i=0;i<12;++i) {
    ++w.player.successful_moves;
    assert(!run(d,w).triggered);
  }
  EncounterControls toggle{};toggle.toggle=true;
  auto switched=run(d,w,toggle);
  assert(switched.status==EncounterStatus::ModeChanged && d.enabled);
  assert(!switched.triggered && d.last_encounter_moves==12);
  assert(!run(d,w).triggered); // no movement, no double trigger
  for(unsigned i=0;i<3;++i) {
    ++w.player.successful_moves;
    assert(!run(d,w).triggered);
  }
  ++w.player.successful_moves;
  assert(run(d,w).triggered);
  assert(d.last_encounter_moves==16);
  assert(!run(d,w).triggered);
  for(unsigned i=0;i<3;++i) {
    ++w.player.successful_moves;assert(!run(d,w).triggered);
  }
  ++w.player.successful_moves;
  assert(run(d,w).triggered);
}

void test_event_pause_defers_until_next_real_step() {
  WorldState w{};EncounterDirector d{};
  EncounterControls toggle{};toggle.toggle=true;
  assert(run(d,w,toggle).enabled);
  for(unsigned i=0;i<3;++i) {
    ++w.player.successful_moves;
    assert(!run(d,w).triggered);
  }
  ++w.player.successful_moves;
  w.pending=Trigger::Event;
  assert(!run(d,w).triggered);
  w.pending=Trigger::None;
  assert(!run(d,w).triggered); // A acknowledged; did not move.
  ++w.player.successful_moves;
  assert(run(d,w).triggered);
  assert(!run(d,w).triggered);
}

void test_area_change_and_snapshot_rebase() {
  WorldState w{};EncounterDirector d{};
  EncounterControls t{};t.toggle=true;
  run(d,w,t);
  for(unsigned i=0;i<3;++i){++w.player.successful_moves;run(d,w);}
  w.area=1;
  ++w.player.successful_moves;
  assert(!run(d,w).triggered);
  assert(d.last_encounter_moves==4);
  for(unsigned i=0;i<3;++i){++w.player.successful_moves;assert(!run(d,w).triggered);}
  ++w.player.successful_moves;
  assert(run(d,w).triggered);
  w.player.successful_moves=2; // restore earlier save / reload
  assert(!run(d,w).triggered);
  assert(d.last_encounter_moves==2);
  for(unsigned i=0;i<4;++i){
    ++w.player.successful_moves;
    const auto r=run(d,w);
    assert(r.triggered==(i==3));
  }
  EncounterControls load{};load.snapshot_restored=true;
  assert(!run(d,w,load).triggered);
  assert(d.last_encounter_moves==6);
}

void test_modal_training_and_existing_battle_never_trigger() {
  WorldState w{};EncounterDirector d{};
  EncounterControls t{};t.toggle=true;run(d,w,t);
  for(unsigned i=0;i<3;++i){++w.player.successful_moves;run(d,w);}
  ++w.player.successful_moves;
  EncounterControls modal{};modal.field_modal=true;
  assert(!run(d,w,modal).triggered);
  assert(!run(d,w).triggered); // time elapsed but no new step
  ++w.player.successful_moves;
  EncounterControls training{};training.training_requested=true;
  assert(!run(d,w,training).triggered);
  ++w.player.successful_moves;
  EncounterControls battle{};battle.battle_active=true;
  battle.toggle=true;
  assert(!run(d,w,battle).triggered);
  assert(d.enabled); // ZR ignored while combat owns input
  ++w.player.successful_moves;
  assert(run(d,w).triggered);
  // Autoplay always disables and resets baseline.
  EncounterControls auto_mode{};auto_mode.manual_mode=false;
  assert(!run(d,w,auto_mode).triggered && !d.enabled);
  assert(!run(d,w).triggered);
}

void test_disabling_is_rearm_not_a_random_encounter() {
  WorldState w{};EncounterDirector d{};
  EncounterControls toggle{};toggle.toggle=true;
  assert(run(d,w,toggle).enabled);
  w.player.successful_moves=3;run(d,w);
  assert(!run(d,w,toggle).enabled);
  for(unsigned i=0;i<8;++i){
    ++w.player.successful_moves;assert(!run(d,w).triggered);
  }
  assert(run(d,w,toggle).enabled);
  assert(!run(d,w).triggered);
  assert(d.last_encounter_moves==11);
}

void test_invalid_state_is_atomic() {
  WorldState w{};EncounterDirector d{};
  w.area=2;
  auto snap=d;
  EncounterControls toggle{};toggle.toggle=true;
  assert(run(d,w,toggle).status==EncounterStatus::InvalidState);
  assert(d.enabled==snap.enabled && d.primed==snap.primed &&
         d.area==snap.area);
  w.area=0;w.pending=static_cast<Trigger>(99);
  assert(run(d,w,toggle).status==EncounterStatus::InvalidState);
  assert(!d.enabled && !d.primed);
}

void test_actual_field_movement_activates_optional_battle() {
  const FieldWorld world=make_demo_world();
  auto field=start_field_runtime(world,19200000,0);
  EncounterDirector encounter{};
  FieldBattleSession battle{};
  constexpr int stride=kRasterWidth+8;
  std::vector<std::uint32_t> pixels(
      static_cast<std::size_t>(stride)*kRasterHeight);
  const PixelTarget target{pixels.data(),kRasterWidth,kRasterHeight,stride};
  std::uint64_t tick=0;
  assert(advance_field_runtime(world,field,tick,{},target).status==
         RuntimeStatus::Rendered);
  EncounterControls toggle{};toggle.toggle=true;
  assert(advance_field_encounters(encounter,field.manual,toggle).enabled);
  // Walk three steps to the first event, acknowledge it with A, then
  // take one more real step by moving left: an encounter is triggered.
  const RuntimeControls right{PadSample{.dpad_right=true}};
  for(unsigned i=0;i<3;++i) {
    tick+=19200000*160/1000;
    assert(advance_field_runtime(world,field,tick,right,target).status==
           RuntimeStatus::Rendered);
    assert(!advance_field_encounters(encounter,field.manual,{}).triggered);
  }
  assert(field.manual.pending==Trigger::Event);
  tick+=320000;
  const RuntimeControls ack{PadSample{.confirm=true}};
  assert(advance_field_runtime(world,field,tick,ack,target).status==
         RuntimeStatus::Rendered);
  assert(field.manual.pending==Trigger::None);
  assert(!advance_field_encounters(encounter,field.manual,{}).triggered);
  tick+=19200000*160/1000;
  const RuntimeControls left{PadSample{.dpad_left=true}};
  assert(advance_field_runtime(world,field,tick,left,target).status==
         RuntimeStatus::Rendered);
  assert(field.manual.player.successful_moves==4);
  const auto encounter_frame=advance_field_encounters(encounter,field.manual,{});
  assert(encounter_frame.triggered);
  FieldBattleSessionInput start{};
  start.open=encounter_frame.triggered;start.manual_mode=true;
  assert(advance_battle_session(battle,start,target).entered);
  assert(battle.active);
  assert(field.manual.area==0 && field.manual.player.x==3);
  assert(advance_battle_session(battle,{.close=true},target).exited);
  assert(field.manual.player.successful_moves==4);
  assert(!advance_field_encounters(encounter,field.manual,{}).triggered);
}
}
int main() {
  test_disabled_is_inert_and_toggle_has_no_immediate_encounter();
  test_event_pause_defers_until_next_real_step();
  test_area_change_and_snapshot_rebase();
  test_modal_training_and_existing_battle_never_trigger();
  test_disabling_is_rearm_not_a_random_encounter();
  test_invalid_state_is_atomic();
  test_actual_field_movement_activates_optional_battle();
}
