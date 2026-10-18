#include "field.hpp"

#include <cstddef>
#include <limits>

namespace wa::field {

bool Map::valid() const noexcept {
  if (width <= 0 || height <= 0 ||
      width > kMaximumDimension || height > kMaximumDimension ||
      tiles.size() != static_cast<std::size_t>(width) *
                          static_cast<std::size_t>(height)) {
    return false;
  }
  for (const char cell : tiles) {
    if (cell != '#' && cell != '.' && cell != '!' && cell != 'E') {
      return false;
    }
  }
  return true;
}

char Map::tile(const int x, const int y) const noexcept {
  if (x < 0 || y < 0 || x >= width || y >= height || !valid()) {
    return '\0';
  }
  return tiles[static_cast<std::size_t>(y) *
                   static_cast<std::size_t>(width) +
               static_cast<std::size_t>(x)];
}

Result step(State& state, const Map& map, const Input& input) noexcept {
  if (!map.valid()) {
    return {Outcome::InvalidMap, Trigger::None};
  }
  if (state.x < 0 || state.y < 0 || state.x >= map.width ||
      state.y >= map.height || map.tile(state.x, state.y) == '#') {
    return {Outcome::InvalidState, Trigger::None};
  }

  const int keys = static_cast<int>(input.up) +
                   static_cast<int>(input.down) +
                   static_cast<int>(input.left) +
                   static_cast<int>(input.right);
  if (keys == 0) {
    return {Outcome::Idle, Trigger::None};
  }
  if (keys != 1) {
    return {Outcome::AmbiguousInput, Trigger::None};
  }

  int dx = 0;
  int dy = 0;
  Direction facing = Direction::None;
  if (input.up) {
    dy = -1;
    facing = Direction::Up;
  } else if (input.down) {
    dy = 1;
    facing = Direction::Down;
  } else if (input.left) {
    dx = -1;
    facing = Direction::Left;
  } else {
    dx = 1;
    facing = Direction::Right;
  }

  // Facing changes on a single attempted input, even if a wall blocks it.
  state.facing = facing;
  const int next_x = state.x + dx;
  const int next_y = state.y + dy;
  const char cell = map.tile(next_x, next_y);
  if (cell == '\0' || cell == '#') {
    return {Outcome::Blocked, Trigger::None};
  }
  if (state.successful_moves == std::numeric_limits<std::uint64_t>::max()) {
    return {Outcome::CounterExhausted, Trigger::None};
  }
  state.x = next_x;
  state.y = next_y;
  ++state.successful_moves;
  if (cell == '!') {
    return {Outcome::Moved, Trigger::Event};
  }
  if (cell == 'E') {
    return {Outcome::Moved, Trigger::Exit};
  }
  return {Outcome::Moved, Trigger::None};
}

}  // namespace wa::field
