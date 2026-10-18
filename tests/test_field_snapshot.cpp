#include "field_snapshot.hpp"
#include <cstdlib>
#include <cstdint>

namespace {
using namespace wa::field;
void check(bool condition) { if (!condition) std::abort(); }

void test_round_trip_preserves_event_and_clock() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  FieldSnapshotSlot slot{};
  check(load_field_snapshot(world, slot, state) == SnapshotOutcome::Empty);
  check(state.player.x == 1 && state.player.successful_moves == 0);
  const PadSample right{.dpad_right = true};
  for (int i = 0; i < 3; ++i) {
    const WorldFrameResult result = advance_world_frame(world, state, right, 160);
    check(result.controller.movement.successful_steps == 1);
  }
  check(state.pending == Trigger::Event && state.player.x == 4);
  check(save_field_snapshot(world, state, slot) == SnapshotOutcome::Stored);
  check(slot.occupied);
  check(advance_world_frame(world, state, PadSample{.confirm = true}, 160)
            .controller.outcome == PadFrameOutcome::Acknowledged);
  check(state.pending == Trigger::None);
  check(load_field_snapshot(world, slot, state) == SnapshotOutcome::Restored);
  check(state.pending == Trigger::Event && state.clock.paused_for_trigger);
  check(state.player.x == 4 && state.player.successful_moves == 3);
  check(!state.decoder.confirm_down);
  check(advance_world_frame(world, state, PadSample{.confirm = true}, 160)
            .controller.outcome == PadFrameOutcome::Acknowledged);
  check(state.pending == Trigger::None && state.clock.carry_ms == 0);
}

void test_bad_snapshots_rejected_without_corrupting_live_state() {
  FieldWorld world = make_demo_world();
  WorldState active = start_world(world);
  FieldSnapshotSlot slot{};
  check(save_field_snapshot(world, active, slot) == SnapshotOutcome::Stored);
  WorldState bad = active;
  bad.area = -1;
  check(save_field_snapshot(world, bad, slot) == SnapshotOutcome::InvalidState);
  check(slot.world.area == 0 && slot.world.player.x == 1);
  bad = active;
  bad.clock.carry_ms = bad.clock.cadence_ms;
  check(save_field_snapshot(world, bad, slot) == SnapshotOutcome::InvalidState);
  bad = active;
  bad.pending = Trigger::Exit;
  bad.clock.paused_for_trigger = true;
  check(save_field_snapshot(world, bad, slot) == SnapshotOutcome::InvalidState);
  const WorldState original = active;
  slot.world.area = 2;
  check(load_field_snapshot(world, slot, active) == SnapshotOutcome::InvalidState);
  check(active.area == original.area && active.player.x == original.player.x);
  slot.world = start_world(world);
  world.areas[1].entrance_x = 0;
  check(load_field_snapshot(world, slot, active) == SnapshotOutcome::InvalidState);
  check(active.player.x == original.player.x);
}
}

int main() {
  test_round_trip_preserves_event_and_clock();
  test_bad_snapshots_rejected_without_corrupting_live_state();
}
