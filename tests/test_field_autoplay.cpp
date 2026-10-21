#include "field_autoplay.hpp"
#include <cstdint>
#include <cstdlib>

namespace {
using namespace wa::field;
void require(bool cond) { if (!cond) std::abort(); }

void test_hold_budget_and_boundaries() {
  const FieldWorld world = make_demo_world();
  AutoplayTrack t = start_field_autoplay(world);
  require(!t.failed && matches_checkpoint(t.scenario.world, 0));
  require(t.wait_ms == 2500);
  require(advance_field_autoplay(world, t, 1000).status == AutoplayStatus::Holding);
  require(t.wait_ms == 1500 && t.scenario.world.player.successful_moves == 0);
  require(advance_field_autoplay(world, t, 1000).status == AutoplayStatus::Holding);
  require(t.wait_ms == 500);
  require(advance_field_autoplay(world, t, 499).status == AutoplayStatus::Holding);
  require(t.wait_ms == 1 && t.scenario.world.player.x == 1);
  const AutoplayFrame first = advance_field_autoplay(world, t, 1);
  require(first.status == AutoplayStatus::Stepped && t.wait_ms == 350);
  require(t.scenario.world.player.x == 2);
  require(advance_field_autoplay(world, t, 0).status == AutoplayStatus::Holding);
  require(t.wait_ms == 350);
  const AutoplayFrame second = advance_field_autoplay(world, t, 1000);
  require(second.status == AutoplayStatus::Stepped);
  require(t.scenario.world.player.x == 3 && t.wait_ms == 350);
  const AutoplayFrame event = advance_field_autoplay(world, t, 1000);
  require(event.status == AutoplayStatus::Checkpoint && event.checkpoint == 1);
  require(t.scenario.world.pending == Trigger::Event && t.wait_ms == 2500);
  require(advance_field_autoplay(world, t, 1000).status == AutoplayStatus::Holding);
  require(t.scenario.world.pending == Trigger::Event);
}

void test_invalid_delta_cannot_consume_frame() {
  const FieldWorld world = make_demo_world();
  AutoplayTrack t = start_field_autoplay(world);
  require(advance_field_autoplay(world, t, 1001).status ==
          AutoplayStatus::InvalidDelta);
  require(t.wait_ms == 2500 && t.scenario.segment == 0 &&
          t.scenario.world.player.successful_moves == 0 && !t.failed);
  require(advance_field_autoplay(world, t, 1000).status ==
          AutoplayStatus::Holding);
  require(t.wait_ms == 1500);
}

void test_full_script_and_repeatability_with_irregular_frames() {
  const FieldWorld world = make_demo_world();
  AutoplayTrack a = start_field_autoplay(world);
  AutoplayTrack b = start_field_autoplay(world);
  int checkpoints = 1;
  int ticks = 0;
  int guard = 0;
  while (!a.scenario.complete) {
    require(++guard < 1000);
    // Alternating small and late frames never permit catch-up steps.
    const std::uint32_t delta = guard % 2 ? 57u : 1000u;
    const AutoplayFrame result_a = advance_field_autoplay(world, a, delta);
    const AutoplayFrame result_b = advance_field_autoplay(world, b, delta);
    require(result_a.status == result_b.status &&
            result_a.checkpoint == result_b.checkpoint);
    require(a.wait_ms == b.wait_ms &&
            a.scenario.segment == b.scenario.segment &&
            a.scenario.world.area == b.scenario.world.area &&
            a.scenario.world.player.x == b.scenario.world.player.x &&
            a.scenario.world.player.y == b.scenario.world.player.y);
    if (result_a.status == AutoplayStatus::Checkpoint) {
      require(result_a.checkpoint == checkpoints++);
      ++ticks;
    } else if (result_a.status == AutoplayStatus::Stepped) {
      ++ticks;
    } else {
      require(result_a.status == AutoplayStatus::Holding);
    }
  }
  require(ticks == 23 && checkpoints == 5 &&
          matches_checkpoint(a.scenario.world, 4) &&
          a.scenario.world.player.successful_moves == 20);
  require(advance_field_autoplay(world, a, 1000).status ==
          AutoplayStatus::Finished);
  a = start_field_autoplay(world);
  require(a.wait_ms == 2500 && !a.failed &&
          matches_checkpoint(a.scenario.world, 0));
}

void test_changed_map_fails_closed_and_stays_invalid() {
  FieldWorld world = make_demo_world();
  AutoplayTrack t = start_field_autoplay(world);
  world.areas[1].entrance_x = 0;
  require(advance_field_autoplay(world, t, 1000).status ==
          AutoplayStatus::Holding);
  require(advance_field_autoplay(world, t, 1000).status ==
          AutoplayStatus::Holding);
  require(advance_field_autoplay(world, t, 500).status ==
          AutoplayStatus::Invalid);
  require(t.failed && t.scenario.world.player.successful_moves == 0);
  world = make_demo_world();
  require(advance_field_autoplay(world, t, 1000).status ==
          AutoplayStatus::Invalid);
  world.areas[0].entrance_x = 2;
  require(start_field_autoplay(world).failed);
}
}  // namespace
int main() {
  test_hold_budget_and_boundaries();
  test_invalid_delta_cannot_consume_frame();
  test_full_script_and_repeatability_with_irregular_frames();
  test_changed_map_fails_closed_and_stays_invalid();
}
