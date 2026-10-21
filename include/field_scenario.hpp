#pragma once
#include "field_world.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {
// Shared asset-free replay, the same inputs for reference PNGs and NRO.
struct ScenarioSegment {
  PadSample input{};
  std::uint8_t repetitions = 1;
  Trigger final_trigger = Trigger::None;
  bool acknowledge = false;
  bool change_area = false;
  int checkpoint = -1;
};
constexpr std::array<ScenarioSegment, 9> kFieldScenario{{
    {{.dpad_right = true}, 3, Trigger::Event, false, false, 1},
    {{.confirm = true}, 1, Trigger::None, true, false, -1},
    {{.dpad_left = true}, 1, Trigger::None, false, false, -1},
    {{.dpad_down = true}, 4, Trigger::None, false, false, -1},
    {{.dpad_right = true}, 3, Trigger::Exit, false, false, 2},
    {{.confirm = true}, 1, Trigger::None, true, true, 3},
    {{.dpad_down = true}, 4, Trigger::None, false, false, -1},
    {{.dpad_right = true}, 5, Trigger::Exit, false, false, -1},
    {{.confirm = true}, 1, Trigger::None, true, true, 4}
}};

struct ScenarioCheckpoint {
  int area;
  int x;
  int y;
  std::uint32_t moves;
  Trigger pending;
};
constexpr std::array<ScenarioCheckpoint, 5> kFieldCheckpoints{{
    {0, 1, 1, 0, Trigger::None},
    {0, 4, 1, 3, Trigger::Event},
    {0, 6, 5, 11, Trigger::Exit},
    {1, 1, 1, 11, Trigger::None},
    {0, 1, 1, 20, Trigger::None}
}};
[[nodiscard]] inline bool matches_checkpoint(
    const WorldState& state, int index) noexcept {
  if (index < 0 || index >= static_cast<int>(kFieldCheckpoints.size()))
    return false;
  const ScenarioCheckpoint& expected =
      kFieldCheckpoints[static_cast<std::size_t>(index)];
  return state.area == expected.area &&
         state.player.x == expected.x &&
         state.player.y == expected.y &&
         state.player.successful_moves == expected.moves &&
         state.pending == expected.pending &&
         state.clock.paused_for_trigger ==
             (expected.pending != Trigger::None);
}

enum class ScenarioStatus { Advanced, Checkpoint, Finished, Invalid };
struct ScenarioResult {
  ScenarioStatus status = ScenarioStatus::Advanced;
  int checkpoint = -1;
};
struct ScenarioTrack {
  WorldState world{};
  std::size_t segment = 0;
  std::uint8_t repetition = 0;
  bool complete = false;
  bool invalid = false;
};
[[nodiscard]] inline ScenarioTrack start_field_scenario(
    const FieldWorld& world) noexcept {
  ScenarioTrack result{};
  result.world = start_world(world);
  result.invalid = !world.valid() || !matches_checkpoint(result.world, 0);
  return result;
}
// On divergence, fail closed: never publish a plausible but wrong image.
[[nodiscard]] inline ScenarioResult advance_field_scenario(
    const FieldWorld& world, ScenarioTrack& track) noexcept {
  if (track.invalid) return {ScenarioStatus::Invalid};
  if (track.complete) return {ScenarioStatus::Finished};
  if (track.segment >= kFieldScenario.size() || !world.valid()) {
    track.invalid = true;
    return {ScenarioStatus::Invalid};
  }
  const ScenarioSegment& command = kFieldScenario[track.segment];
  if (command.repetitions == 0 ||
      track.repetition >= command.repetitions) {
    track.invalid = true;
    return {ScenarioStatus::Invalid};
  }
  const WorldFrameResult result =
      advance_world_frame(world, track.world, command.input, 160);
  const bool last = track.repetition + 1 == command.repetitions;
  const Trigger expected_trigger = last ? command.final_trigger : Trigger::None;
  bool valid = false;
  if (command.acknowledge) {
    valid = result.controller.outcome == PadFrameOutcome::Acknowledged &&
            result.controller.movement.successful_steps == 0 &&
            result.controller.movement.trigger == Trigger::None &&
            result.area_changed == command.change_area &&
            track.world.pending == Trigger::None;
  } else {
    valid = result.controller.outcome == PadFrameOutcome::Advanced &&
            result.controller.movement.successful_steps == 1 &&
            result.controller.movement.trigger == expected_trigger &&
            result.controller.movement.status ==
               (expected_trigger == Trigger::None
                   ? TimedStatus::Moved : TimedStatus::Triggered) &&
            !result.area_changed;
  }
  if (!valid) {
    track.invalid = true;
    return {ScenarioStatus::Invalid};
  }
  ++track.repetition;
  if (!last) return {ScenarioStatus::Advanced};
  track.repetition = 0;
  ++track.segment;
  if (command.checkpoint >= 0 &&
      !matches_checkpoint(track.world, command.checkpoint)) {
    track.invalid = true;
    return {ScenarioStatus::Invalid};
  }
  if (track.segment == kFieldScenario.size()) track.complete = true;
  if (command.checkpoint >= 0)
    return {ScenarioStatus::Checkpoint, command.checkpoint};
  return {ScenarioStatus::Advanced};
}
} // namespace wa::field
