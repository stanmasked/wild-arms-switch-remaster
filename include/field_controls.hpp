#pragma once

#include "field.hpp"
#include "field_timing.hpp"

#include <cstdint>

namespace wa::field {

// Host-only controller snapshot. A future libnx frontend must translate
// its hardware button and analog-axis API to this platform-neutral format.
struct PadSample {
  bool dpad_up = false;
  bool dpad_down = false;
  bool dpad_left = false;
  bool dpad_right = false;
  bool confirm = false;
  std::int16_t stick_x = 0;
  std::int16_t stick_y = 0;  // Positive means down in this field contract.
};

constexpr int kFieldStickThreshold = 16000;

struct PadDecoder {
  bool confirm_down = false;
};

struct PadCommand {
  Input direction{};
  bool confirm_pressed = false;  // Rising edge, not an auto-repeated hold.
};

// D-pad has precedence over analog input, including conflicting D-pad keys.
// Both axes of a diagonal are preserved. The existing field core rejects
// multiple directions as ambiguous instead of picking an arbitrary axis.
[[nodiscard]] inline PadCommand decode_pad(
    PadDecoder& decoder, const PadSample& sample) noexcept {
  PadCommand result{};
  result.confirm_pressed = sample.confirm && !decoder.confirm_down;
  decoder.confirm_down = sample.confirm;

  if (sample.dpad_up || sample.dpad_down ||
      sample.dpad_left || sample.dpad_right) {
    result.direction = {sample.dpad_up, sample.dpad_down,
                        sample.dpad_left, sample.dpad_right};
  } else {
    const int x = static_cast<int>(sample.stick_x);
    const int y = static_cast<int>(sample.stick_y);
    result.direction = {
        y <= -kFieldStickThreshold,
        y >= kFieldStickThreshold,
        x <= -kFieldStickThreshold,
        x >= kFieldStickThreshold};
  }
  return result;
}

enum class PadFrameOutcome { Advanced, Acknowledged };

struct PadFrameResult {
  PadFrameOutcome outcome = PadFrameOutcome::Advanced;
  TimedResult movement{};
};

// Transactional preflight for invalid game/clock/delta state: these errors
// must not consume a button edge or acknowledge a pending event.
// Confirm acknowledges only on a fresh press, and consumes the entire frame
// without movement. This prevents one press from skipping an event and
// walking into another cell in the same update.
[[nodiscard]] inline PadFrameResult advance_pad_frame(
    PadDecoder& decoder, MovementClock& clock, State& state, const Map& map,
    const PadSample& sample, std::uint32_t delta_ms) noexcept {
  if (!clock.valid())
    return {PadFrameOutcome::Advanced, {TimedStatus::InvalidClock}};
  if (delta_ms > kMaximumMovementDeltaMs)
    return {PadFrameOutcome::Advanced, {TimedStatus::InvalidDelta}};
  const Result preflight = step(state, map, {});
  if (preflight.outcome == Outcome::InvalidMap)
    return {PadFrameOutcome::Advanced, {TimedStatus::InvalidMap}};
  if (preflight.outcome == Outcome::InvalidState)
    return {PadFrameOutcome::Advanced, {TimedStatus::InvalidState}};

  const PadCommand command = decode_pad(decoder, sample);
  if (command.confirm_pressed && clock.paused_for_trigger) {
    // Clock invariants were checked above.
    (void)acknowledge_trigger(clock);
    return {PadFrameOutcome::Acknowledged, {TimedStatus::Idle}};
  }
  return {PadFrameOutcome::Advanced,
          advance_timed(clock, state, map, command.direction, delta_ms)};
}

}  // namespace wa::field
