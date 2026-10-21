#pragma once

#include "field_world.hpp"

namespace wa::field {

// Volatile, in-memory manual exploration checkpoint. No filesystem storage.
enum class SnapshotOutcome { Stored, Restored, Empty, InvalidState };

struct FieldSnapshotSlot {
  WorldState world{};
  bool occupied = false;
};

// A saved world must be structurally valid before it may be restored.
// Do not let a corrupt pending trigger resume on the wrong terrain tile.
[[nodiscard]] inline bool valid_field_snapshot(
    const FieldWorld& world, const WorldState& state) noexcept {
  if (!world.valid() || state.area < 0 || state.area >= kFieldAreaCount ||
      !state.clock.valid() ||
      (state.pending != Trigger::None && state.pending != Trigger::Event &&
       state.pending != Trigger::Exit) ||
      state.clock.paused_for_trigger != (state.pending != Trigger::None))
    return false;

  const Map& map = world.areas[static_cast<std::size_t>(state.area)].map;
  State candidate = state.player;
  const Result probe = step(candidate, map, {});
  if (probe.outcome == Outcome::InvalidMap ||
      probe.outcome == Outcome::InvalidState)
    return false;
  if (state.pending != Trigger::None) {
    const char expected = state.pending == Trigger::Exit ? 'E' : '!';
    if (map.tile(state.player.x, state.player.y) != expected)
      return false;
  }
  return true;
}

// Reject malformed states without altering the previous valid snapshot.
[[nodiscard]] inline SnapshotOutcome save_field_snapshot(
    const FieldWorld& world, const WorldState& state,
    FieldSnapshotSlot& slot) noexcept {
  if (!valid_field_snapshot(world, state))
    return SnapshotOutcome::InvalidState;
  slot.world = state;
  slot.occupied = true;
  return SnapshotOutcome::Stored;
}

// Loading the empty slot is a harmless no-op. A corrupt slot fails closed.
[[nodiscard]] inline SnapshotOutcome load_field_snapshot(
    const FieldWorld& world, const FieldSnapshotSlot& slot,
    WorldState& state) noexcept {
  if (!slot.occupied) return SnapshotOutcome::Empty;
  if (!valid_field_snapshot(world, slot.world))
    return SnapshotOutcome::InvalidState;
  state = slot.world;
  return SnapshotOutcome::Restored;
}

}  // namespace wa::field
