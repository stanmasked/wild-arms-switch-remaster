#include "field.hpp"

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
}
