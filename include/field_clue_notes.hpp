#pragma once

#include "field_discovery.hpp"

namespace wa::field {

// Original placeholder narrative for the two asset-free demo events.
// Only keyed coordinates select presentation text. No text enters saves,
// journals, gameplay state or original PS1 asset pipelines.
struct FieldClueNote {
  const char* title;
  const char* detail;
};

[[nodiscard]] constexpr FieldClueNote field_clue_note(
    const FieldClue& clue) noexcept {
  if (clue.area == 0 && clue.x == 4 && clue.y == 1)
    return {"OLD RADIO NOTE", "SIGNAL IN STATIC"};
  if (clue.area == 1 && clue.x == 4 && clue.y == 3)
    return {"SILENT RELAY", "AN ECHO ANSWERS"};
  // Future authored synthetic maps remain safe, but never pass off a
  // generic/unknown coordinate as an original Wild Arms lore entry.
  return {"FIELD OBSERVATION", "NO FIELD NOTES"};
}

} // namespace wa::field
