#include "field.hpp"
#include "field_timing.hpp"
#include "field_view.hpp"

#include <cstdint>
#include <cstdlib>
#include <limits>

namespace {
using namespace wa::field;

void require(bool ok) {
  if (!ok) std::abort();
}

Map village() {
  return {7, 5,
          "#######"
          "#..!..#"
          "#.#...#"
          "#...E.#"
          "#######"};
}

void test_valid_map_and_coordinates() {
  const auto m = village();
  require(m.valid());
  require(m.tile(1, 1) == '.');
  require(m.tile(3, 1) == '!');
  require(m.tile(4, 3) == 'E');
  require(m.tile(-1, 1) == '\0');
  require(m.tile(7, 1) == '\0');
  require(m.tile(0, 5) == '\0');
  require(m.tile(1, -1) == '\0');
}

void test_invalid_maps() {
  require(!Map{0, 2, ".."}.valid());
  require(!Map{2, 0, ".."}.valid());
  require(!Map{-1, 1, "."}.valid());
  require(!Map{65, 1, std::string(65, '.')}.valid());
  require(!Map{1, 65, std::string(65, '.')}.valid());
  require(!Map{2, 2, "..."}.valid());
  require(!Map{2, 2, "....."}.valid());
  require(!Map{2, 2, ".?.."}.valid());
  require(Map{64, 64, std::string(4096, '.')}.valid());
  require(Map{1, 1, "."}.valid());
}

void test_idle_and_ambiguous_input_no_state_change() {
  const auto m = village();
  State s{1, 1};
  require(step(s, m, {}).outcome == Outcome::Idle);
  require(step(s, m, {.up = true, .down = true}).outcome ==
          Outcome::AmbiguousInput);
  require(step(s, m, {.left = true, .right = true}).outcome ==
          Outcome::AmbiguousInput);
  require(step(s, m, {.down = true, .right = true}).outcome ==
          Outcome::AmbiguousInput);
  require(s.x == 1 && s.y == 1 && s.successful_moves == 0);
  require(s.facing == Direction::Down);
}

void test_walls_and_border_block_without_events() {
  const auto m = village();
  State s{1, 1};
  require(step(s, m, {.up = true}).outcome == Outcome::Blocked);
  require(s.facing == Direction::Up);
  require(step(s, m, {.left = true}).outcome == Outcome::Blocked);
  require(s.facing == Direction::Left);
  require(s.x == 1 && s.y == 1 && s.successful_moves == 0);
  require(step(s, m, {.right = true}).outcome == Outcome::Moved);
  require(step(s, m, {.down = true}).outcome == Outcome::Blocked);
  require(s.facing == Direction::Down);
  require(s.x == 2 && s.y == 1 && s.successful_moves == 1);
}

void test_event_only_on_entry_and_exit() {
  const auto m = village();
  State s{1, 1};
  require(step(s, m, {.right = true}).trigger == Trigger::None);
  const auto entered = step(s, m, {.right = true});
  require(entered.outcome == Outcome::Moved);
  require(entered.trigger == Trigger::Event);
  require(s.x == 3 && s.y == 1);
  require(step(s, m, {}).trigger == Trigger::None);
  require(step(s, m, {.up = true}).trigger == Trigger::None);
  require(step(s, m, {.right = true}).trigger == Trigger::None);
  require(step(s, m, {.left = true}).trigger == Trigger::Event);
  require(s.successful_moves == 4);
}

void test_exit_event_on_tile_entry() {
  const auto m = village();
  State s{3, 3};
  const auto entered = step(s, m, {.right = true});
  require(entered.outcome == Outcome::Moved);
  require(entered.trigger == Trigger::Exit);
  require(s.x == 4 && s.y == 3 && s.successful_moves == 1);
  require(step(s, m, {}).trigger == Trigger::None);
  require(step(s, m, {.up = true}).trigger == Trigger::None);
  require(step(s, m, {.down = true}).trigger == Trigger::Exit);
}

void test_invalid_player_state_fails_without_mutation() {
  const auto m = village();
  for (const State input : {State{-1, 1}, State{1, -1},
                            State{7, 1}, State{1, 5},
                            State{0, 0}}) {
    State s = input;
    const auto r = step(s, m, {.right = true});
    require(r.outcome == Outcome::InvalidState && r.trigger == Trigger::None);
    require(s.x == input.x && s.y == input.y &&
            s.facing == input.facing &&
            s.successful_moves == input.successful_moves);
  }
}

void test_invalid_map_does_not_turn_player() {
  State s{0, 0, Direction::Left, 2};
  const auto r = step(s, Map{2, 2, "?..."}, {.right = true});
  require(r.outcome == Outcome::InvalidMap);
  require(r.trigger == Trigger::None);
  require(s.x == 0 && s.y == 0 && s.facing == Direction::Left);
  require(s.successful_moves == 2);
}

void test_outside_map_boundary_and_no_overflow() {
  const Map m{1, 1, "."};
  State s{0, 0};
  require(step(s, m, {.left = true}).outcome == Outcome::Blocked);
  require(step(s, m, {.up = true}).outcome == Outcome::Blocked);
  require(step(s, m, {.right = true}).outcome == Outcome::Blocked);
  require(step(s, m, {.down = true}).outcome == Outcome::Blocked);
  require(s.x == 0 && s.y == 0 && s.successful_moves == 0);
}

void test_counter_overflow_refused_without_position_change() {
  const auto m = village();
  State s{1, 1, Direction::Down,
          std::numeric_limits<std::uint64_t>::max()};
  const auto r = step(s, m, {.right = true});
  require(r.outcome == Outcome::CounterExhausted);
  require(r.trigger == Trigger::None);
  require(s.x == 1 && s.y == 1);
  require(s.successful_moves ==
          std::numeric_limits<std::uint64_t>::max());
}

void test_deterministic_replay() {
  const auto m = village();
  const Input commands[] = {
      {.right = true}, {.right = true}, {.up = true},
      {.right = true}, {.right = true}, {.down = true},
      {.left = true}, {.down = true}, {},
      {.down = true, .left = true}};
  State first{1, 1};
  State second{1, 1};
  for (const Input command : commands) {
    const auto a = step(first, m, command);
    const auto b = step(second, m, command);
    require(a.outcome == b.outcome && a.trigger == b.trigger);
    require(first.x == second.x && first.y == second.y);
    require(first.facing == second.facing);
    require(first.successful_moves == second.successful_moves);
  }
  require(first.x == 4 && first.y == 3);
  require(first.successful_moves == 7);
  require(first.facing == Direction::Down);
}


void test_timed_accumulation_and_released_input() {
  const auto m = village();
  State s{1, 1};
  MovementClock clock;
  require(advance_timed(clock, s, m, {.right = true}, 100).status ==
          TimedStatus::Waiting);
  require(advance_timed(clock, s, m, {.right = true}, 59).status ==
          TimedStatus::Waiting);
  require(s.x == 1 && clock.carry_ms == 159);
  const auto moved = advance_timed(clock, s, m, {.right = true}, 1);
  require(moved.status == TimedStatus::Moved &&
          moved.successful_steps == 1 && moved.attempted_steps == 1);
  require(s.x == 2 && s.successful_moves == 1 && clock.carry_ms == 0);
  require(advance_timed(clock, s, m, {.right = true}, 120).status ==
          TimedStatus::Waiting);
  require(advance_timed(clock, s, m, {}, 100).status == TimedStatus::Idle);
  require(clock.carry_ms == 0 && clock.held == Direction::None);
  require(advance_timed(clock, s, m, {.right = true}, 40).status ==
          TimedStatus::Waiting);
  require(advance_timed(clock, s, m, {.right = true}, 120).status ==
          TimedStatus::Triggered);
  require(s.x == 3 && clock.paused_for_trigger);
}

void test_timed_partition_invariant_without_trigger() {
  const Map m{12, 3,
              "############"
              "#..........#"
              "############"};
  require(m.valid());
  State large{1, 1};
  State small{1, 1};
  MovementClock ca, cb;
  const auto once = advance_timed(ca, large, m, {.right = true}, 480);
  require(once.status == TimedStatus::Moved &&
          once.attempted_steps == 3 && once.successful_steps == 3);
  for (int i = 0; i < 6; ++i)
    (void)advance_timed(cb, small, m, {.right = true}, 80);
  require(large.x == small.x && large.y == small.y);
  require(large.successful_moves == small.successful_moves);
  require(large.facing == small.facing);
  require(ca.carry_ms == cb.carry_ms && ca.held == cb.held);
  require(large.x == 4 && large.successful_moves == 3);
}

void test_timed_direction_change_and_blocked_facing() {
  const auto m = village();
  State s{1, 1};
  MovementClock clock;
  require(advance_timed(clock, s, m, {.right = true}, 120).status ==
          TimedStatus::Waiting);
  require(advance_timed(clock, s, m, {.down = true}, 100).status ==
          TimedStatus::Waiting);
  require(s.x == 1 && s.y == 1 && clock.carry_ms == 100);
  require(advance_timed(clock, s, m, {.down = true}, 60).status ==
          TimedStatus::Moved);
  require(s.y == 2 && s.facing == Direction::Down);
  const auto collision = advance_timed(clock, s, m, {.left = true}, 320);
  require(collision.status == TimedStatus::Blocked &&
          collision.attempted_steps == 2 && collision.successful_steps == 0);
  require(s.x == 1 && s.y == 2 && s.facing == Direction::Left);
}

void test_timed_event_pause_and_resume() {
  const auto m = village();
  State s{1, 1};
  MovementClock clock;
  const auto event = advance_timed(clock, s, m, {.right = true}, 800);
  require(event.status == TimedStatus::Triggered &&
          event.trigger == Trigger::Event);
  require(event.attempted_steps == 2 && event.successful_steps == 2);
  require(s.x == 3 && s.successful_moves == 2);
  require(clock.paused_for_trigger && clock.carry_ms == 0 &&
          clock.held == Direction::None);
  const auto paused = advance_timed(clock, s, m, {.right = true}, 1000);
  require(paused.status == TimedStatus::Paused &&
          paused.attempted_steps == 0 && s.x == 3);
  require(acknowledge_trigger(clock));
  require(!acknowledge_trigger(clock));
  require(advance_timed(clock, s, m, {.left = true}, 159).status ==
          TimedStatus::Waiting);
  require(advance_timed(clock, s, m, {.left = true}, 1).status ==
          TimedStatus::Moved);
  require(s.x == 2);
  const auto repeat = advance_timed(clock, s, m, {.right = true}, 160);
  require(repeat.status == TimedStatus::Triggered &&
          repeat.trigger == Trigger::Event && s.x == 3);
}

void test_timed_exit_pause() {
  const auto m = village();
  State s{3, 3};
  MovementClock clock;
  const auto exit = advance_timed(clock, s, m, {.right = true}, 160);
  require(exit.status == TimedStatus::Triggered &&
          exit.trigger == Trigger::Exit && s.x == 4);
  require(advance_timed(clock, s, m, {.left = true}, 160).status ==
          TimedStatus::Paused);
  require(s.x == 4 && clock.paused_for_trigger);
}

void test_timed_rejects_malformed_inputs_without_mutation() {
  const auto m = village();
  State s{1, 1};
  MovementClock clock;
  require(advance_timed(clock, s, m, {.right = true}, 100).status ==
          TimedStatus::Waiting);
  const MovementClock before = clock;
  require(advance_timed(clock, s, m, {.right = true}, 1001).status ==
          TimedStatus::InvalidDelta);
  require(advance_timed(clock, s, m,
                        {.down = true, .right = true}, 60).status ==
          TimedStatus::AmbiguousInput);
  require(advance_timed(clock, s, Map{2, 2, "??.."},
                        {.right = true}, 60).status ==
          TimedStatus::InvalidMap);
  require(clock.carry_ms == before.carry_ms && clock.held == before.held);
  require(s.x == 1 && s.y == 1 && s.successful_moves == 0);
  State bad{-1, 1};
  require(advance_timed(clock, bad, m, {.right = true}, 60).status ==
          TimedStatus::InvalidState);
  require(bad.x == -1 && clock.carry_ms == before.carry_ms);
  clock.cadence_ms = 0;
  require(advance_timed(clock, s, m, {.right = true}, 60).status ==
          TimedStatus::InvalidClock);
  clock.cadence_ms = 160;
  clock.carry_ms = 160;
  require(advance_timed(clock, s, m, {.right = true}, 60).status ==
          TimedStatus::InvalidClock);
  clock.carry_ms = 100;
  clock.held = static_cast<Direction>(99);
  require(advance_timed(clock, s, m, {.right = true}, 60).status ==
          TimedStatus::InvalidClock);
  require(s.x == 1 && s.successful_moves == 0);
}

void test_timed_counter_overflow_safety() {
  const auto m = village();
  State s{1, 1, Direction::Down,
          std::numeric_limits<std::uint64_t>::max()};
  MovementClock clock;
  const auto result = advance_timed(clock, s, m, {.right = true}, 160);
  require(result.status == TimedStatus::CounterExhausted &&
          result.attempted_steps == 1 && result.successful_steps == 0);
  require(result.trigger == Trigger::None && s.x == 1 && s.y == 1);
  require(s.facing == Direction::Right &&
          s.successful_moves == std::numeric_limits<std::uint64_t>::max());
}


void test_viewport_camera_and_player_facing() {
  const auto m = village();
  State s{1, 1, Direction::Up};
  RenderFrame f;
  require(build_view(f, m, s, {3, 3}) == RenderOutcome::Ready);
  require(f.ready && f.width == 3 && f.height == 3);
  require(f.world_left == 0 && f.world_top == 0);
  require(f.at(1, 1) && f.at(1, 1)->player);
  require(f.at(1, 1)->terrain == CellKind::Floor);
  require(glyph_for(*f.at(1, 1), f.player_facing) == '^');
  require(glyph_for(*f.at(0, 0), f.player_facing) == '#');
  require(!f.at(-1, 0) && !f.at(3, 0) && !f.at(0, 3));

  s = State{5, 3, Direction::Left};
  require(build_view(f, m, s, {3, 3}) == RenderOutcome::Ready);
  require(f.world_left == 4 && f.world_top == 2);
  require(f.at(1, 1)->player && f.at(1, 1)->terrain == CellKind::Floor);
  require(glyph_for(*f.at(1, 1), f.player_facing) == '<');
  require(glyph_for(*f.at(2, 2), f.player_facing) == '#');
}

void test_viewport_preserves_underlying_event_and_exit() {
  const auto m = village();
  RenderFrame f;
  State event{3, 1, Direction::Right};
  require(build_view(f, m, event, {3, 3}) == RenderOutcome::Ready);
  require(f.world_left == 2 && f.world_top == 0);
  require(f.at(1, 1)->terrain == CellKind::Event);
  require(f.at(1, 1)->player);
  require(glyph_for(*f.at(1, 1), f.player_facing) == '>');
  require(glyph_for({CellKind::Event, false}, Direction::Down) == '!');
  State exit{4, 3, Direction::None};
  require(build_view(f, m, exit, {3, 3}) == RenderOutcome::Ready);
  require(f.at(1, 1)->terrain == CellKind::Exit);
  require(glyph_for(*f.at(1, 1), f.player_facing) == '@');
}

void test_viewport_small_map_padding() {
  const Map m{2, 1, ".E"};
  RenderFrame f;
  require(build_view(f, m, State{0, 0}, {5, 3}) ==
          RenderOutcome::Ready);
  require(f.world_left == -1 && f.world_top == -1);
  require(f.at(0, 0)->terrain == CellKind::Outside);
  require(glyph_for(*f.at(0, 0), Direction::Down) == ' ');
  require(f.at(1, 1)->player &&
          f.at(1, 1)->terrain == CellKind::Floor);
  require(f.at(2, 1)->terrain == CellKind::Exit);
  require(!f.at(2, 1)->player);
  require(f.at(4, 2)->terrain == CellKind::Outside);
}

void test_viewport_invalid_inputs_leave_frame_unchanged() {
  const auto m = village();
  RenderFrame f;
  require(build_view(f, m, State{1, 1}, {3, 3}) ==
          RenderOutcome::Ready);
  const int x = f.world_left, y = f.world_top;
  const char glyph = glyph_for(*f.at(1, 1), f.player_facing);
  require(build_view(f, m, State{1, 1}, {0, 3}) ==
          RenderOutcome::InvalidViewport);
  require(build_view(f, m, State{1, 1}, {33, 3}) ==
          RenderOutcome::InvalidViewport);
  require(build_view(f, m, State{1, 1}, {3, -1}) ==
          RenderOutcome::InvalidViewport);
  require(build_view(f, Map{2, 2, "?"}, State{1, 1}, {3, 3}) ==
          RenderOutcome::InvalidMap);
  require(build_view(f, m, State{0, 0}, {3, 3}) ==
          RenderOutcome::InvalidState);
  require(build_view(f, m, State{7, 0}, {3, 3}) ==
          RenderOutcome::InvalidState);
  require(build_view(f, m,
                     State{1, 1, static_cast<Direction>(99)}, {3, 3}) ==
          RenderOutcome::InvalidState);
  require(f.ready && f.width == 3 && f.height == 3);
  require(f.world_left == x && f.world_top == y);
  require(glyph_for(*f.at(1, 1), f.player_facing) == glyph);
}

void test_viewport_maximum_and_uninitialized_frame() {
  RenderFrame f;
  require(!f.at(0, 0));
  const Map m{64, 64, std::string(4096, '.')};
  require(build_view(f, m, State{32, 32}, {32, 32}) ==
          RenderOutcome::Ready);
  require(f.world_left == 16 && f.world_top == 16);
  require(f.at(16, 16) && f.at(16, 16)->player);
  require(f.at(31, 31) &&
          f.at(31, 31)->terrain == CellKind::Floor);
  require(!f.at(32, 31) && !f.at(31, 32));
  int actors = 0;
  for (int y = 0; y < f.height; ++y)
    for (int x = 0; x < f.width; ++x)
      actors += static_cast<int>(f.at(x, y)->player);
  require(actors == 1);
}

void test_viewport_deterministic_replay() {
  const auto m = village();
  const Input inputs[] = {
      {.right = true}, {.right = true}, {.left = true},
      {.down = true}, {.down = true}, {.right = true}};
  State a{1, 1}, b{1, 1};
  for (const auto input : inputs) {
    (void)step(a, m, input);
    (void)step(b, m, input);
    RenderFrame fa, fb;
    require(build_view(fa, m, a, {5, 3}) == RenderOutcome::Ready);
    require(build_view(fb, m, b, {5, 3}) == RenderOutcome::Ready);
    require(fa.world_left == fb.world_left &&
            fa.world_top == fb.world_top &&
            fa.player_facing == fb.player_facing);
    for (int y = 0; y < 3; ++y)
      for (int x = 0; x < 5; ++x) {
        require(fa.at(x, y)->terrain == fb.at(x, y)->terrain);
        require(fa.at(x, y)->player == fb.at(x, y)->player);
      }
  }
}

}  // namespace

int main() {
  test_valid_map_and_coordinates();
  test_invalid_maps();
  test_idle_and_ambiguous_input_no_state_change();
  test_walls_and_border_block_without_events();
  test_event_only_on_entry_and_exit();
  test_exit_event_on_tile_entry();
  test_invalid_player_state_fails_without_mutation();
  test_invalid_map_does_not_turn_player();
  test_outside_map_boundary_and_no_overflow();
  test_counter_overflow_refused_without_position_change();
  test_deterministic_replay();
  test_timed_accumulation_and_released_input();
  test_timed_partition_invariant_without_trigger();
  test_timed_direction_change_and_blocked_facing();
  test_timed_event_pause_and_resume();
  test_timed_exit_pause();
  test_timed_rejects_malformed_inputs_without_mutation();
  test_timed_counter_overflow_safety();
  test_viewport_camera_and_player_facing();
  test_viewport_preserves_underlying_event_and_exit();
  test_viewport_small_map_padding();
  test_viewport_invalid_inputs_leave_frame_unchanged();
  test_viewport_maximum_and_uninitialized_frame();
  test_viewport_deterministic_replay();
}
