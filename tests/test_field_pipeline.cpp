#include "field.hpp"
#include "field_timing.hpp"
#include "field_view.hpp"

#include <array>
#include <cstdlib>
#include <cstdint>

using namespace wa::field;

namespace {
void check(bool ok) {
  if (!ok) std::abort();
}

struct Sample {
  Input input;
  std::uint32_t elapsed_ms;
  bool acknowledge_before = false;
};

struct Simulation {
  State state{1, 1};
  MovementClock clock{};
  RenderFrame frame{};
  std::uint32_t events = 0;
  std::uint32_t exits = 0;
  std::uint32_t moves = 0;
};

// This intentionally drives both the movement clock and viewport: tests
// cannot accidentally pass by checking only a standalone movement function.
void apply(Simulation& sim, const Map& map, const Sample& sample) {
  if (sample.acknowledge_before)
    check(acknowledge_trigger(sim.clock));
  const TimedResult result =
      advance_timed(sim.clock, sim.state, map, sample.input, sample.elapsed_ms);
  check(result.status != TimedStatus::InvalidClock &&
        result.status != TimedStatus::InvalidMap &&
        result.status != TimedStatus::InvalidState &&
        result.status != TimedStatus::InvalidDelta);
  sim.moves += result.successful_steps;
  if (result.trigger == Trigger::Event) ++sim.events;
  if (result.trigger == Trigger::Exit) ++sim.exits;
  check(build_view(sim.frame, map, sim.state, Viewport{5, 3}) ==
        RenderOutcome::Ready);
}

void same(const Simulation& a, const Simulation& b) {
  check(a.state.x == b.state.x && a.state.y == b.state.y);
  check(a.state.facing == b.state.facing);
  check(a.state.successful_moves == b.state.successful_moves);
  check(a.clock.cadence_ms == b.clock.cadence_ms &&
        a.clock.carry_ms == b.clock.carry_ms &&
        a.clock.held == b.clock.held &&
        a.clock.paused_for_trigger == b.clock.paused_for_trigger);
  check(a.events == b.events && a.exits == b.exits && a.moves == b.moves);
  check(a.frame.width == b.frame.width &&
        a.frame.height == b.frame.height &&
        a.frame.world_left == b.frame.world_left &&
        a.frame.world_top == b.frame.world_top &&
        a.frame.player_facing == b.frame.player_facing);
  for (int y = 0; y < a.frame.height; ++y)
    for (int x = 0; x < a.frame.width; ++x) {
      const RenderCell* ca = a.frame.at(x, y);
      const RenderCell* cb = b.frame.at(x, y);
      check(ca != nullptr && cb != nullptr);
      check(ca->terrain == cb->terrain && ca->player == cb->player);
    }
}

void deterministic_replay_across_event_and_exit() {
  const Map map{9, 5,
                "#########"
                "#..!....#"
                "#.......#"
                "#....E..#"
                "#########"};
  check(map.valid());
  // Includes blocked input, ambiguity, idle, an event pause, explicit
  // acknowledgement and an exit. Values intentionally cross cadence bounds.
  const std::array<Sample, 15> trace{{
      {{.up = true}, 160},
      {{.right = true}, 80},
      {{.right = true}, 80},
      {{.right = true, .left = true}, 160},
      {{.right = true}, 160},
      {{.right = true}, 1000},
      {{.down = true}, 160, true},
      {{.right = true}, 320},
      {{.down = true}, 160},
      {{.down = true}, 160},
      {{.right = true}, 160},
      {{.left = true}, 160},
      {{.right = true}, 160},
      {{}, 0},
      {{.right = true}, 160}
  }};
  Simulation a, b;
  for (const Sample& sample : trace) {
    apply(a, map, sample);
    apply(b, map, sample);
    same(a, b);
  }
  check(a.events == 1);
  check(a.state.successful_moves == a.moves);
  check(a.frame.ready);
}

void frame_partition_invariance_before_trigger() {
  const Map map{9, 3,
                "#########"
                "#.......#"
                "#########"};
  check(map.valid());
  Simulation a, b;
  apply(a, map, {{.right = true}, 480});
  for (int i = 0; i < 6; ++i)
    apply(b, map, {{.right = true}, 80});
  same(a, b);
  check(a.state.x == 4 && a.moves == 3);
}

void mutation_of_rendered_snapshot_does_not_mutate_map_or_state() {
  const Map map{3, 3, "####.####"};
  check(map.valid());
  Simulation a;
  apply(a, map, {{}, 0});
  const State before = a.state;
  a.frame.cells[0].terrain = CellKind::Event;
  a.frame.cells[0].player = true;
  check(map.tiles == "####.####");
  check(a.state.x == before.x && a.state.y == before.y);
}
}  // namespace

int main() {
  deterministic_replay_across_event_and_exit();
  frame_partition_invariance_before_trigger();
  mutation_of_rendered_snapshot_does_not_mutate_map_or_state();
}
