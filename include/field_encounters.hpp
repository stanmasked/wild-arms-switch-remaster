#pragma once
// Stage 349: optional deterministic field encounters, no ROM content.
// Off by default; an explicit Switch ZR edge enables step encounters.
// Does not serialize into, or change, the 40-byte exploration save format.
#include "field_world.hpp"

#include <cstdint>

namespace wa::field {

constexpr std::uint64_t kEncounterStepInterval = 4;

struct EncounterDirector {
  bool enabled = false;
  bool primed = false;
  int area = -1;
  std::uint64_t last_observed_moves = 0;
  std::uint64_t last_encounter_moves = 0;
};

struct EncounterControls {
  bool toggle = false;           // Switch ZR rising edge.
  bool manual_mode = true;       // Never affect the canonical autoplay.
  bool battle_active = false;    // Battle already owns the controller.
  bool training_requested = false; // Switch R takes precedence over ZR.
  bool snapshot_restored = false;
  bool field_modal = false;      // Journal or pending save/inspect command.
};

enum class EncounterStatus : std::uint8_t {
  Idle, ModeChanged, Triggered, InvalidState
};
struct EncounterFrame {
  EncounterStatus status = EncounterStatus::Idle;
  bool enabled = false;
  bool triggered = false;
};

// Observes only movement already validated/published by field runtime.
// Encounter scheduling never changes WorldState, discovery ledger,
// quicksave, input decoder, the battle engine or the framebuffer.
[[nodiscard]] inline EncounterFrame advance_field_encounters(
    EncounterDirector& current, const WorldState& field,
    const EncounterControls& input) noexcept {
  if (field.area < 0 || field.area >= kFieldAreaCount ||
      (field.pending != Trigger::None && field.pending != Trigger::Event &&
       field.pending != Trigger::Exit))
    return {EncounterStatus::InvalidState, current.enabled, false};

  EncounterDirector next = current;
  const std::uint64_t moves = field.player.successful_moves;
  const bool rebased = !next.primed || next.area != field.area ||
      input.snapshot_restored || moves < next.last_observed_moves;
  if (rebased) {
    next.primed = true;
    next.area = field.area;
    next.last_observed_moves = moves;
    next.last_encounter_moves = moves;
  }
  const bool freshly_moved = moves > next.last_observed_moves;
  next.last_observed_moves = moves;

  // Autoplay must remain byte-for-byte the previous opt-out behavior.
  // Re-entering manual play starts from a fresh local movement baseline.
  if (!input.manual_mode) {
    next.enabled = false;
    next.last_encounter_moves = moves;
    current = next;
    return {};
  }

  // An R training fight has precedence. Ignore ZR while in a fight or
  // while the field journal is modal. A ZR toggle cannot also encounter.
  if (input.toggle && !input.battle_active &&
      !input.training_requested && !input.field_modal) {
    next.enabled = !next.enabled;
    next.last_encounter_moves = moves;
    current = next;
    return {EncounterStatus::ModeChanged, current.enabled, false};
  }
  if (!next.enabled || !freshly_moved || rebased ||
      input.battle_active || input.training_requested ||
      input.field_modal || field.pending != Trigger::None) {
    current = next;
    return {EncounterStatus::Idle, current.enabled, false};
  }

  // Avoid subtraction overflow even when movement counter approaches
  // UINT64_MAX: a restored/corrupt counter is rebased first.
  if (moves - next.last_encounter_moves < kEncounterStepInterval) {
    current = next;
    return {EncounterStatus::Idle, current.enabled, false};
  }

  next.last_encounter_moves = moves;
  current = next;
  return {EncounterStatus::Triggered, current.enabled, true};
}

} // namespace wa::field
