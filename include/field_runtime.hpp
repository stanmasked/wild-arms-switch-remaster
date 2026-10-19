#pragma once

#include "field_autoplay.hpp"
#include "field_discovery.hpp"
#include "field_frame_ticks.hpp"
#include "field_inspection_ui.hpp"
#include "field_journal_view.hpp"
#include "field_pixels.hpp"
#include "field_snapshot.hpp"
#include "field_view.hpp"

#include <cstddef>
#include <cstdint>

namespace wa::field {

// Exact host/Switch field pipeline. The platform only owns the controller
// sample, current monotonic tick, and writable linear framebuffer.
// Inspection is ephemeral UI: never serialized to the world save record.
constexpr std::uint32_t kFieldInspectionDurationMs = 900;
struct FieldInspection {
  Trigger kind = Trigger::None;
  int area = -1;
  int x = -1;
  int y = -1;
  std::uint32_t remaining_ms = 0;
  bool logged = false;
};

struct FieldRuntime {
  WorldState manual{};
  FieldSnapshotSlot quicksave{};
  AutoplayTrack demo{};
  FrameTickClock timer{};
  RenderFrame view{};
  FieldInspection inspection{};
  FieldDiscoveryJournal discoveries{};
  bool autoplay = false;
};

enum class RuntimeStatus {
  Rendered,
  InvalidWorld,
  InvalidClock,
  InvalidTarget,
  InvalidSimulation,
  InvalidView,
  InvalidRaster
};

struct RuntimeFrame {
  RuntimeStatus status = RuntimeStatus::InvalidWorld;
  FrameTickStatus tick_status = FrameTickStatus::Ready;
  std::uint32_t delta_ms = 0;
  bool autoplay = false;
  bool changed_area = false;
  Trigger inspected = Trigger::None;
  bool clue_recorded = false;
  bool clue_already_recorded = false;
  std::size_t clue_count = 0;
  bool journal_visible = false;
  int checkpoint = -1;
  TimedStatus movement_status = TimedStatus::Idle;
  // Not a persistent save; does not write to disk.
  bool snapshot_stored = false;
  bool snapshot_restored = false;
  bool snapshot_empty = false;
};

// Buttons X and B are host-supplied rising edges. In manual mode A is a
// normal held button decoded by the existing PadDecoder.
struct RuntimeControls {
  PadSample pad{};
  bool start_demo = false;
  bool cancel_demo = false;
  bool save_snapshot = false;
  bool load_snapshot = false;
  // Hold L for a read-only, modal session journal. No gameplay input is
  // processed while held; all five preceding aggregate fields are stable.
  bool view_journal = false;
};

[[nodiscard]] inline FieldRuntime start_field_runtime(
    const FieldWorld& world, std::uint64_t tick_frequency,
    std::uint64_t initial_tick) noexcept {
  FieldRuntime result{};
  result.manual = start_world(world);
  result.demo = start_field_autoplay(world);
  result.timer = make_frame_tick_clock(tick_frequency, initial_tick);
  return result;
}

[[nodiscard]] inline bool runtime_has_valid_target(
    const PixelTarget& target) noexcept {
  return target.pixels != nullptr &&
         target.width == kRasterWidth &&
         target.height == kRasterHeight &&
         target.stride_pixels >= kRasterWidth &&
         target.stride_pixels <= 8192;
}

// Validate + compute the next gameplay state before drawing. Rejecting
// malformed target/world/time never consumes input or the counter sample.
// This function is deliberately the single entry point for native and host.
[[nodiscard]] inline RuntimeFrame advance_field_runtime(
    const FieldWorld& world, FieldRuntime& current,
    std::uint64_t current_tick, const RuntimeControls& controls,
    const PixelTarget& target) noexcept {
  if (!world.valid()) return {RuntimeStatus::InvalidWorld};
  if (!current.timer.valid()) return {RuntimeStatus::InvalidClock};
  if (!runtime_has_valid_target(target))
    return {RuntimeStatus::InvalidTarget};
  // In manual mode a corrupt clue ledger or world snapshot must fail
  // before sampling the clock, accepting B, or drawing *any* framebuffer.
  // Checking only on L would let an invalid ledger run unnoticed until
  // the player first opened the journal.
  if (!current.autoplay &&
      (!valid_field_snapshot(world, current.manual) ||
       !valid_discovery_journal(world, current.discoveries)))
    return {RuntimeStatus::InvalidSimulation};

  FieldRuntime next = current;
  const FrameTickDelta elapsed =
      advance_frame_ticks(next.timer, current_tick);
  if (elapsed.status == FrameTickStatus::InvalidClock)
    return {RuntimeStatus::InvalidClock};

  RuntimeFrame response{};
  response.tick_status = elapsed.status;
  response.delta_ms = elapsed.milliseconds;
  response.clue_count = next.discoveries.count;

  // The L-held modal freezes gameplay *and* the inspection highlight
  // clock. Otherwise a player can lose a still-readable A inspection
  // simply by consulting the clue journal.
  if (!(controls.view_journal && !next.autoplay)) {
    if (elapsed.milliseconds >= next.inspection.remaining_ms) {
      next.inspection = FieldInspection{};
    } else {
      next.inspection.remaining_ms -= elapsed.milliseconds;
    }
  }

  bool mode_switched = false;
  if (controls.start_demo && !(controls.view_journal && !next.autoplay)) {
    next.demo = start_field_autoplay(world);
    if (next.demo.failed) return {RuntimeStatus::InvalidSimulation};
    next.autoplay = true;
    mode_switched = true;
  } else if (next.autoplay && controls.cancel_demo) {
    next.manual = start_world(world);
    next.autoplay = false;
    mode_switched = true;
  }

  if (mode_switched) next.inspection = FieldInspection{};

  if (!mode_switched && next.autoplay) {
    const AutoplayFrame outcome =
        advance_field_autoplay(world, next.demo, elapsed.milliseconds);
    if (outcome.status == AutoplayStatus::Invalid ||
        outcome.status == AutoplayStatus::InvalidDelta)
      return {RuntimeStatus::InvalidSimulation};
    response.checkpoint = outcome.checkpoint;
  } else if (!mode_switched && !controls.view_journal) {
    // Holding L owns its entire frame, so it cannot move, inspect,
    // acknowledge events, save, load or record new clues.
    // A snapshot operation owns its entire frame. It must neither step the
    // player nor acknowledge an event, even if movement/A is held.
    if (controls.save_snapshot && controls.load_snapshot)
      return {RuntimeStatus::InvalidSimulation};
    if (controls.save_snapshot) {
      next.inspection = FieldInspection{};
      if (save_field_snapshot(world, next.manual, next.quicksave) !=
          SnapshotOutcome::Stored)
        return {RuntimeStatus::InvalidSimulation};
      response.snapshot_stored = true;
    } else if (controls.load_snapshot) {
      next.inspection = FieldInspection{};
      const SnapshotOutcome restored =
          load_field_snapshot(world, next.quicksave, next.manual);
      if (restored == SnapshotOutcome::InvalidState)
        return {RuntimeStatus::InvalidSimulation};
      response.snapshot_restored = restored == SnapshotOutcome::Restored;
      response.snapshot_empty = restored == SnapshotOutcome::Empty;
    } else {
      const int old_x = next.manual.player.x;
      const int old_y = next.manual.player.y;
      const Direction old_facing = next.manual.player.facing;
      const WorldFrameResult outcome =
          advance_world_frame(world, next.manual, controls.pad,
                              elapsed.milliseconds);
      response.movement_status = outcome.controller.movement.status;
      response.changed_area = outcome.area_changed;
      response.inspected = outcome.inspected;
      // Do not leave a stale target highlighted if the player has
      // moved or turned to a different direction, even into a wall.
      if (outcome.area_changed ||
          outcome.controller.movement.trigger != Trigger::None ||
          next.manual.player.x != old_x ||
          next.manual.player.y != old_y ||
          next.manual.player.facing != old_facing)
        next.inspection = FieldInspection{};
      if (outcome.inspected != Trigger::None) {
        int dx = 0;
        int dy = 0;
        switch (next.manual.player.facing) {
          case Direction::Up: dy = -1; break;
          case Direction::Down: dy = 1; break;
          case Direction::Left: dx = -1; break;
          case Direction::Right: dx = 1; break;
          case Direction::None: break;
        }
        next.inspection = {outcome.inspected, next.manual.area,
                           next.manual.player.x + dx,
                           next.manual.player.y + dy,
                           kFieldInspectionDurationMs, false};
      }
      // In manual mode B records a clue only from a still-visible
      // inspection of an adjacent event. It is a separate, explicit
      // action: merely looking at an object grants no progress.
      if (controls.cancel_demo && !next.autoplay &&
          next.inspection.kind == Trigger::Event &&
          next.inspection.remaining_ms > 0 &&
          next.inspection.area == next.manual.area &&
          next.manual.pending == Trigger::None &&
          next.manual.player.x == old_x &&
          next.manual.player.y == old_y &&
          next.manual.player.facing == old_facing) {
        const DiscoveryResult discovery = record_discovery(
            world, next.discoveries, next.inspection.area,
            next.inspection.x, next.inspection.y);
        if (discovery == DiscoveryResult::Recorded ||
            discovery == DiscoveryResult::PreviouslyRecorded) {
          next.inspection.logged = true;
          next.inspection.remaining_ms = kFieldInspectionDurationMs;
          response.clue_recorded = discovery == DiscoveryResult::Recorded;
          response.clue_already_recorded =
              discovery == DiscoveryResult::PreviouslyRecorded;
          response.clue_count = next.discoveries.count;
        }
      }
      switch (response.movement_status) {
        case TimedStatus::InvalidMap:
        case TimedStatus::InvalidState:
        case TimedStatus::InvalidClock:
        case TimedStatus::InvalidDelta:
          return {RuntimeStatus::InvalidSimulation};
        default: break;
      }
    }
  }

  const WorldState& shown = next.autoplay ? next.demo.scenario.world
                                         : next.manual;
  if (shown.area < 0 || shown.area >= kFieldAreaCount)
    return {RuntimeStatus::InvalidSimulation};
  const Map& map = world.areas[static_cast<std::size_t>(shown.area)].map;
  RenderFrame frame{};
  if (build_view(frame, map, shown.player, {11, 7}) !=
      RenderOutcome::Ready)
    return {RuntimeStatus::InvalidView};
  if (validate_raster(target, frame, shown.area) != RasterOutcome::Ready)
    return {RuntimeStatus::InvalidRaster};

  if (draw_field_pixels(target, frame, shown.clock.paused_for_trigger,
                        shown.area) != RasterOutcome::Ready)
    return {RuntimeStatus::InvalidRaster};

  if (!next.autoplay && controls.view_journal) {
    if (!draw_discovery_journal(target, world, next.discoveries))
      return {RuntimeStatus::InvalidSimulation};
    response.journal_visible = true;
  } else if (!next.autoplay &&
      next.inspection.kind != Trigger::None &&
      next.inspection.remaining_ms > 0 &&
      next.inspection.area == shown.area) {
    const bool target_visible = draw_field_inspection(
        target, frame, next.inspection.x, next.inspection.y,
        next.inspection.kind);
    if (target_visible)
      (void)draw_inspection_caption(target, next.inspection.kind,
                                    next.inspection.logged);
    else
      next.inspection = FieldInspection{};
  }

  next.view = frame;
  current = next;
  response.status = RuntimeStatus::Rendered;
  response.autoplay = next.autoplay;
  return response;
}

}  // namespace wa::field
