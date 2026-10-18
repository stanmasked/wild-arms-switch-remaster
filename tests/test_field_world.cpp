#include "field_world.hpp"
#include "field_view.hpp"

#include <array>
#include <cstdlib>
#include <cstdint>

namespace {
using namespace wa::field;

void require(bool ok) {
  if (!ok) std::abort();
}

FieldWorld simple_world() {
  FieldWorld world{};
  world.areas[0] = {Map{7, 3, "#######" "#.!E..#" "#######"}, 1, 1};
  world.areas[1] = {Map{7, 3, "#######" "#.E...#" "#######"}, 1, 1};
  return world;
}

void test_world_layout_and_start() {
  const FieldWorld demo = make_demo_world();
  require(demo.valid());
  require(demo.areas[0].map.tiles != demo.areas[1].map.tiles);
  WorldState first = start_world(demo);
  require(first.area == 0 && first.player.x == 1 && first.player.y == 1);
  require(first.player.successful_moves == 0);
  require(first.pending == Trigger::None && !first.clock.paused_for_trigger);
}

void test_event_then_transition_then_return() {
  const FieldWorld world = simple_world();
  require(world.valid());
  WorldState game = start_world(world);
  const PadSample right{.dpad_right = true};
  const PadSample right_and_a{.dpad_right = true, .confirm = true};
  const PadSample only_a{.confirm = true};

  auto event = advance_world_frame(world, game, right, 160);
  require(event.controller.movement.status == TimedStatus::Triggered);
  require(event.controller.movement.trigger == Trigger::Event);
  require(!event.area_changed && game.area == 0 && game.player.x == 2);
  require(game.pending == Trigger::Event && game.clock.paused_for_trigger);

  const auto acknowledge_event =
      advance_world_frame(world, game, right_and_a, 160);
  require(acknowledge_event.controller.outcome == PadFrameOutcome::Acknowledged);
  require(!acknowledge_event.area_changed && game.area == 0);
  require(game.pending == Trigger::None && !game.clock.paused_for_trigger);
  require(game.player.x == 2 && game.player.successful_moves == 1);

  const auto exit = advance_world_frame(world, game, right_and_a, 160);
  require(exit.controller.movement.trigger == Trigger::Exit);
  require(game.pending == Trigger::Exit && game.player.x == 3);
  require(game.area == 0 && !exit.area_changed);

  require(advance_world_frame(world, game, right_and_a, 160)
              .controller.movement.status == TimedStatus::Paused);
  require(game.area == 0 && game.player.x == 3);
  (void)advance_world_frame(world, game, {}, 0);

  const auto transfer = advance_world_frame(world, game, only_a, 160);
  require(transfer.area_changed);
  require(transfer.controller.outcome == PadFrameOutcome::Acknowledged);
  require(game.area == 1 && game.player.x == 1 && game.player.y == 1);
  require(game.player.facing == Direction::Down);
  require(game.player.successful_moves == 2);
  require(!game.clock.paused_for_trigger && game.clock.carry_ms == 0);
  require(game.pending == Trigger::None);

  const auto second_exit = advance_world_frame(world, game, right, 160);
  require(second_exit.controller.movement.trigger == Trigger::Exit);
  require(game.area == 1 && game.player.x == 2);
  const auto return_to_first = advance_world_frame(world, game, only_a, 160);
  require(return_to_first.area_changed && game.area == 0);
  require(game.player.x == 1 && game.player.y == 1);
  require(game.player.successful_moves == 3);
}

void test_rejects_bad_world_and_state_without_mutation() {
  FieldWorld world = simple_world();
  WorldState game = start_world(world);
  const PadSample pressed{.confirm = true, .dpad_right = true};
  world.areas[1].entrance_x = 0;  // Wall, not a spawn.
  require(advance_world_frame(world, game, pressed, 160)
              .controller.movement.status == TimedStatus::InvalidMap);
  require(!game.decoder.confirm_down && game.player.x == 1);
  world = simple_world();

  game.area = -1;
  require(advance_world_frame(world, game, pressed, 160)
              .controller.movement.status == TimedStatus::InvalidState);
  game.area = 0;
  game.pending = Trigger::Exit;
  require(advance_world_frame(world, game, pressed, 160)
              .controller.movement.status == TimedStatus::InvalidState);
  game.pending = Trigger::None;
  require(!game.clock.paused_for_trigger && !game.decoder.confirm_down);

  require(advance_world_frame(world, game, pressed, 1001)
              .controller.movement.status == TimedStatus::InvalidDelta);
  require(!game.decoder.confirm_down && game.player.successful_moves == 0);
}

struct Sample {
  PadSample pad{};
  std::uint32_t duration_ms = 0;
};

void same(const WorldState& a, const WorldState& b) {
  require(a.area == b.area && a.pending == b.pending);
  require(a.player.x == b.player.x && a.player.y == b.player.y);
  require(a.player.facing == b.player.facing);
  require(a.player.successful_moves == b.player.successful_moves);
  require(a.clock.held == b.clock.held);
  require(a.clock.carry_ms == b.clock.carry_ms);
  require(a.clock.paused_for_trigger == b.clock.paused_for_trigger);
  require(a.decoder.confirm_down == b.decoder.confirm_down);
}

void test_deterministic_two_area_viewport_replay() {
  const FieldWorld world = simple_world();
  const std::array<Sample, 9> commands{{
      {{.dpad_right = true}, 160},
      {{.dpad_right = true, .confirm = true}, 160},
      {{.dpad_right = true, .confirm = true}, 160},
      {{.dpad_right = true, .confirm = true}, 160},
      {{}, 0},
      {{.confirm = true}, 160},
      {{.dpad_right = true}, 160},
      {{.confirm = true}, 160},
      {{.dpad_right = true}, 80}
  }};
  WorldState a = start_world(world);
  WorldState b = start_world(world);
  std::uint32_t transitions = 0;
  for (const Sample& cmd : commands) {
    const auto ra = advance_world_frame(world, a, cmd.pad, cmd.duration_ms);
    const auto rb = advance_world_frame(world, b, cmd.pad, cmd.duration_ms);
    require(ra.area_changed == rb.area_changed);
    require(ra.controller.outcome == rb.controller.outcome);
    require(ra.controller.movement.status == rb.controller.movement.status);
    require(ra.controller.movement.trigger == rb.controller.movement.trigger);
    if (ra.area_changed) ++transitions;
    same(a, b);

    RenderFrame fa, fb;
    require(build_view(fa, world.areas[a.area].map, a.player, {5, 3}) ==
            RenderOutcome::Ready);
    require(build_view(fb, world.areas[b.area].map, b.player, {5, 3}) ==
            RenderOutcome::Ready);
    require(fa.world_left == fb.world_left && fa.world_top == fb.world_top);
    for (int y = 0; y < fa.height; ++y)
      for (int x = 0; x < fa.width; ++x) {
        require(fa.at(x, y)->terrain == fb.at(x, y)->terrain);
        require(fa.at(x, y)->player == fb.at(x, y)->player);
      }
  }
  require(transitions == 2 && a.area == 0);
  require(a.player.successful_moves == 3);
}

}  // namespace

int main() {
  test_world_layout_and_start();
  test_event_then_transition_then_return();
  test_rejects_bad_world_and_state_without_mutation();
  test_deterministic_two_area_viewport_replay();
}
