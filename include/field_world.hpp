#pragma once

#include "field_controls.hpp"

#include <array>

namespace wa::field {

// Two original synthetic maps; a deliberately small host/Switch reference.
// Scene links are explicit and currently go to the other of two areas.
constexpr int kFieldAreaCount = 2;

struct FieldArea {
  Map map{};
  int entrance_x = 1;
  int entrance_y = 1;

  [[nodiscard]] bool valid() const noexcept {
    return map.valid() && map.tile(entrance_x, entrance_y) == '.';
  }
};

struct FieldWorld {
  std::array<FieldArea, kFieldAreaCount> areas{};

  [[nodiscard]] bool valid() const noexcept {
    for (const FieldArea& area : areas)
      if (!area.valid()) return false;
    return true;
  }
};

struct WorldState {
  int area = 0;
  State player{1, 1};
  MovementClock clock{};
  PadDecoder decoder{};
  Trigger pending = Trigger::None;
};

struct WorldFrameResult {
  PadFrameResult controller{};
  bool area_changed = false;
};

[[nodiscard]] inline WorldState start_world(const FieldWorld& world) noexcept {
  WorldState result{};
  if (world.valid()) {
    result.player.x = world.areas[0].entrance_x;
    result.player.y = world.areas[0].entrance_y;
  }
  return result;
}

// The only handler of world transitions. Triggered exits wait for an A
// rising edge; acknowledgement consumes the current frame without movement.
// The successful-movement counter carries across areas.
[[nodiscard]] inline WorldFrameResult advance_world_frame(
    const FieldWorld& world, WorldState& state,
    const PadSample& sample, std::uint32_t elapsed_ms) noexcept {
  if (!world.valid())
    return {{PadFrameOutcome::Advanced, {TimedStatus::InvalidMap}}, false};
  if (state.area < 0 || state.area >= kFieldAreaCount ||
      !valid_clock_direction(state.player.facing) ||
      (state.pending != Trigger::None &&
       state.pending != Trigger::Event &&
       state.pending != Trigger::Exit))
    return {{PadFrameOutcome::Advanced, {TimedStatus::InvalidState}}, false};

  const Map& map = world.areas[static_cast<std::size_t>(state.area)].map;
  if (state.player.x < 0 || state.player.y < 0 ||
      state.player.x >= map.width || state.player.y >= map.height ||
      map.tile(state.player.x, state.player.y) == '#')
    return {{PadFrameOutcome::Advanced, {TimedStatus::InvalidState}}, false};
  if (state.clock.paused_for_trigger != (state.pending != Trigger::None))
    return {{PadFrameOutcome::Advanced, {TimedStatus::InvalidState}}, false};
  if (state.pending != Trigger::None) {
    const char expected = state.pending == Trigger::Exit ? 'E' : '!';
    if (map.tile(state.player.x, state.player.y) != expected)
      return {{PadFrameOutcome::Advanced, {TimedStatus::InvalidState}}, false};
  }

  WorldFrameResult outcome{
      advance_pad_frame(state.decoder, state.clock, state.player,
                        map, sample, elapsed_ms), false};
  if (outcome.controller.movement.trigger != Trigger::None)
    state.pending = outcome.controller.movement.trigger;

  if (outcome.controller.outcome == PadFrameOutcome::Acknowledged) {
    if (state.pending == Trigger::Exit) {
      state.area = 1 - state.area;
      const FieldArea& next = world.areas[static_cast<std::size_t>(state.area)];
      state.player.x = next.entrance_x;
      state.player.y = next.entrance_y;
      state.player.facing = Direction::Down;
      outcome.area_changed = true;
    }
    state.pending = Trigger::None;
  }
  return outcome;
}

// Synthetic sources: not extracted or reconstructed Wild Arms locations.
[[nodiscard]] inline FieldWorld make_demo_world() {
  FieldWorld world{};
  world.areas[0] = {
      Map{11, 7,
          "###########"
          "#...!.....#"
          "#.#.###.#.#"
          "#...#...#.#"
          "#.#...#...#"
          "#.....E...#"
          "###########"},
      1, 1};
  world.areas[1] = {
      Map{11, 7,
          "###########"
          "#....#....#"
          "#....#....#"
          "#...!...#.#"
          "#..#......#"
          "#.....E...#"
          "###########"},
      1, 1};
  return world;
}

}  // namespace wa::field
