#pragma once

#include <cstdint>
#include <string>

namespace wa::field {

// Asset-free, deterministic grid movement reference.
// '#' is an impassable wall, '.' is floor, '!' is an event, 'E' is an exit.
constexpr int kMaximumDimension = 64;

enum class Direction { None, Up, Down, Left, Right };
enum class Trigger { None, Event, Exit };
enum class Outcome {
  Idle,
  InvalidMap,
  InvalidState,
  AmbiguousInput,
  Blocked,
  CounterExhausted,
  Moved
};

struct Map {
  int width = 0;
  int height = 0;
  std::string tiles;  // Owned row-major bytes, exactly width * height.

  [[nodiscard]] bool valid() const noexcept;
  [[nodiscard]] char tile(int x, int y) const noexcept;
};

struct Input {
  bool up = false;
  bool down = false;
  bool left = false;
  bool right = false;
};

struct State {
  int x = 0;
  int y = 0;
  Direction facing = Direction::Down;
  std::uint64_t successful_moves = 0;
};

struct Result {
  Outcome outcome = Outcome::Idle;
  Trigger trigger = Trigger::None;
};

// One input sampling step: at most one cardinal tile of movement.
// Multi-direction input has no implicit priority, avoiding input-order drift.
// Failed moves produce no trigger; an event triggers only upon entering a tile.
[[nodiscard]] Result step(State& state, const Map& map,
                          const Input& input) noexcept;

}  // namespace wa::field
