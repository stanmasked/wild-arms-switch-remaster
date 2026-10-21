#pragma once
#include "field_scenario.hpp"
#include <cstdint>

namespace wa::field {

// Pure timing driver for the asset-free scenario. No libnx dependencies.
// This is a capture-friendly wall-clock schedule, NOT a gameplay benchmark.
constexpr std::uint32_t kAutoplayCheckpointHoldMs = 2500;
constexpr std::uint32_t kAutoplayStepHoldMs = 350;

struct AutoplayTrack {
  ScenarioTrack scenario{};
  std::uint32_t wait_ms = kAutoplayCheckpointHoldMs;
  bool failed = false;
};

enum class AutoplayStatus {
  Holding, Stepped, Checkpoint, Finished, InvalidDelta, Invalid
};
struct AutoplayFrame {
  AutoplayStatus status = AutoplayStatus::Holding;
  int checkpoint = -1;
};

[[nodiscard]] inline AutoplayTrack start_field_autoplay(
    const FieldWorld& world) noexcept {
  AutoplayTrack result{};
  result.scenario = start_field_scenario(world);
  result.failed = result.scenario.invalid;
  return result;
}

// A frame advances at most ONE logical scenario tick. Discard excess elapsed
// time at the boundary rather than fast-forwarding through several scenes.
// This intentionally permits pause/resume and variable frame pacing without
// skipping checkpoints or consuming input twice.
[[nodiscard]] inline AutoplayFrame advance_field_autoplay(
    const FieldWorld& world, AutoplayTrack& track,
    std::uint32_t delta_ms) noexcept {
  if (track.failed || track.scenario.invalid)
    return {AutoplayStatus::Invalid};
  if (delta_ms > kMaximumMovementDeltaMs)
    return {AutoplayStatus::InvalidDelta};
  if (track.scenario.complete)
    return {AutoplayStatus::Finished};
  if (track.wait_ms > delta_ms) {
    track.wait_ms -= delta_ms;
    return {AutoplayStatus::Holding};
  }
  // Timer expires. No carry-over because a single delayed applet frame must
  // not trigger multiple steps; the next frame starts a fresh hold.
  const ScenarioResult result = advance_field_scenario(world, track.scenario);
  if (result.status == ScenarioStatus::Invalid) {
    track.failed = true;
    return {AutoplayStatus::Invalid};
  }
  if (result.status == ScenarioStatus::Finished)
    return {AutoplayStatus::Finished};
  track.wait_ms = result.status == ScenarioStatus::Checkpoint
                      ? kAutoplayCheckpointHoldMs : kAutoplayStepHoldMs;
  if (result.status == ScenarioStatus::Checkpoint)
    return {AutoplayStatus::Checkpoint, result.checkpoint};
  return {AutoplayStatus::Stepped};
}
}  // namespace wa::field
