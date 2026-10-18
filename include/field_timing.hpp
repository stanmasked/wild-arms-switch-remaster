#pragma once

#include "field.hpp"

#include <cstdint>

namespace wa::field {

// Integer-millisecond host reference. Callers own the clock and input trace.
// Large updates are rejected instead of silently clamped or losing game time.
constexpr std::uint32_t kMinimumMovementCadenceMs = 40;
constexpr std::uint32_t kMaximumMovementCadenceMs = 1000;
constexpr std::uint32_t kMaximumMovementDeltaMs = 1000;

[[nodiscard]] constexpr bool valid_clock_direction(Direction direction) noexcept {
  switch (direction) {
    case Direction::None:
    case Direction::Up:
    case Direction::Down:
    case Direction::Left:
    case Direction::Right:
      return true;
  }
  return false;
}

struct MovementClock {
  std::uint32_t cadence_ms = 160;
  std::uint32_t carry_ms = 0;
  Direction held = Direction::None;
  bool paused_for_trigger = false;

  [[nodiscard]] constexpr bool valid() const noexcept {
    return cadence_ms >= kMinimumMovementCadenceMs &&
           cadence_ms <= kMaximumMovementCadenceMs &&
           carry_ms < cadence_ms && valid_clock_direction(held) &&
           (!paused_for_trigger ||
            (carry_ms == 0 && held == Direction::None));
  }
};

enum class TimedStatus {
  Idle,
  Waiting,
  Moved,
  Blocked,
  Triggered,
  Paused,
  CounterExhausted,
  AmbiguousInput,
  InvalidClock,
  InvalidDelta,
  InvalidMap,
  InvalidState
};

struct TimedResult {
  TimedStatus status = TimedStatus::Idle;
  Trigger trigger = Trigger::None;
  std::uint32_t attempted_steps = 0;
  std::uint32_t successful_steps = 0;
};

// A gameplay layer over step(). Each held direction consumes a fixed cadence.
// Switching direction or releasing all keys resets partial time. A triggered
// event/exit pauses movement until the owner explicitly acknowledges it.
// No wall, event or exit can be skipped by a long but valid frame.
[[nodiscard]] inline TimedResult advance_timed(
    MovementClock& clock, State& state, const Map& map, const Input& input,
    std::uint32_t delta_ms) noexcept {
  if (!clock.valid()) return {TimedStatus::InvalidClock};
  if (delta_ms > kMaximumMovementDeltaMs)
    return {TimedStatus::InvalidDelta};

  // step() validates map and position before considering empty input and
  // never mutates state for empty input. Reuse that single source of truth.
  const Result probe = step(state, map, {});
  if (probe.outcome == Outcome::InvalidMap)
    return {TimedStatus::InvalidMap};
  if (probe.outcome == Outcome::InvalidState)
    return {TimedStatus::InvalidState};

  if (clock.paused_for_trigger) return {TimedStatus::Paused};

  const int pressed = static_cast<int>(input.up) +
                      static_cast<int>(input.down) +
                      static_cast<int>(input.left) +
                      static_cast<int>(input.right);
  if (pressed > 1) return {TimedStatus::AmbiguousInput};
  if (pressed == 0) {
    clock.carry_ms = 0;
    clock.held = Direction::None;
    return {TimedStatus::Idle};
  }

  const Direction direction =
      input.up ? Direction::Up
               : input.down ? Direction::Down
                            : input.left ? Direction::Left : Direction::Right;
  if (clock.held != direction) {
    clock.carry_ms = 0;
    clock.held = direction;
  }

  // The validated cadence and delta bound this to at most 25 attempts per
  // call. Work is independent of frame partitioning for unchanged input,
  // except at an intentional event/exit pause boundary.
  const std::uint32_t total = clock.carry_ms + delta_ms;
  const std::uint32_t attempts = total / clock.cadence_ms;
  clock.carry_ms = total % clock.cadence_ms;
  if (attempts == 0) return {TimedStatus::Waiting};

  TimedResult result{TimedStatus::Waiting};
  for (std::uint32_t i = 0; i < attempts; ++i) {
    const Result step_result = step(state, map, input);
    ++result.attempted_steps;
    switch (step_result.outcome) {
      case Outcome::Moved:
        ++result.successful_steps;
        result.status = TimedStatus::Moved;
        if (step_result.trigger != Trigger::None) {
          result.status = TimedStatus::Triggered;
          result.trigger = step_result.trigger;
          clock.paused_for_trigger = true;
          clock.carry_ms = 0;
          clock.held = Direction::None;
          return result;
        }
        break;
      case Outcome::Blocked:
        result.status = TimedStatus::Blocked;
        break;
      case Outcome::CounterExhausted:
        result.status = TimedStatus::CounterExhausted;
        return result;
      case Outcome::InvalidMap:
        result.status = TimedStatus::InvalidMap;
        return result;
      case Outcome::InvalidState:
        result.status = TimedStatus::InvalidState;
        return result;
      case Outcome::Idle:
      case Outcome::AmbiguousInput:
        // Impossible after validation of a single held direction.
        result.status = TimedStatus::InvalidState;
        return result;
    }
  }
  return result;
}

// Called only after the gameplay owner handles the pending event/transition.
// A new hold must earn a full cadence; no old frame debt is replayed.
[[nodiscard]] inline bool acknowledge_trigger(MovementClock& clock) noexcept {
  if (!clock.valid() || !clock.paused_for_trigger) return false;
  clock.paused_for_trigger = false;
  clock.carry_ms = 0;
  clock.held = Direction::None;
  return true;
}

}  // namespace wa::field
