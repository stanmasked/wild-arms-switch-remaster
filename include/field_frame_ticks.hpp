#pragma once

#include <cstdint>

namespace wa::field {

// Integer conversion from the monotonic hardware tick counter to gameplay
// milliseconds. The sub-millisecond remainder is carried between frames.
constexpr std::uint64_t kMinimumFrameTickFrequencyHz = 1000;
constexpr std::uint64_t kMaximumFrameTickFrequencyHz = 1000000000;
constexpr std::uint32_t kMaximumFrameMilliseconds = 1000;

struct FrameTickClock {
  std::uint64_t frequency_hz = 0;
  std::uint64_t previous_tick = 0;
  // Fractional millisecond as a rational numerator / frequency_hz.
  std::uint64_t fractional = 0;

  [[nodiscard]] constexpr bool valid() const noexcept {
    return frequency_hz >= kMinimumFrameTickFrequencyHz &&
           frequency_hz <= kMaximumFrameTickFrequencyHz &&
           fractional < frequency_hz;
  }
};

[[nodiscard]] constexpr FrameTickClock make_frame_tick_clock(
    std::uint64_t frequency_hz, std::uint64_t initial_tick) noexcept {
  return {frequency_hz, initial_tick, 0};
}

enum class FrameTickStatus {
  Ready,
  // A suspended applet or long stall. Drop this frame's gameplay time.
  SkippedPause,
  // Counter went backward or was reset. Resync without advancing gameplay.
  ResetCounter,
  InvalidClock
};

struct FrameTickDelta {
  FrameTickStatus status = FrameTickStatus::InvalidClock;
  std::uint32_t milliseconds = 0;
};

// Rejects invalid clocks without mutation. Tick decreases are treated as
// counter resets rather than unsigned underflow. For a pause >1 second,
// discard elapsed time and fractional carry to avoid huge catch-up movement.
// Multiplication cannot overflow: frequency is bounded at 1e9.
[[nodiscard]] inline FrameTickDelta advance_frame_ticks(
    FrameTickClock& clock, std::uint64_t current_tick) noexcept {
  if (!clock.valid()) return {FrameTickStatus::InvalidClock, 0};
  if (current_tick < clock.previous_tick) {
    clock.previous_tick = current_tick;
    clock.fractional = 0;
    return {FrameTickStatus::ResetCounter, 0};
  }

  const std::uint64_t ticks = current_tick - clock.previous_tick;
  clock.previous_tick = current_tick;

  if (ticks > clock.frequency_hz) {
    clock.fractional = 0;
    return {FrameTickStatus::SkippedPause, 0};
  }

  // ticks <= frequency_hz, hence each update is at most 1000 ms.
  // Convert by full seconds + the remaining fractional second to avoid
  // losing fractions from 16.667ms display frames.
  const std::uint64_t full_seconds = ticks / clock.frequency_hz;
  const std::uint64_t rest_ticks = ticks % clock.frequency_hz;
  const std::uint64_t numerator =
      rest_ticks * 1000u + clock.fractional;
  const std::uint64_t milliseconds =
      full_seconds * 1000u + numerator / clock.frequency_hz;
  clock.fractional = numerator % clock.frequency_hz;
  return {FrameTickStatus::Ready,
          static_cast<std::uint32_t>(milliseconds)};
}

}  // namespace wa::field
