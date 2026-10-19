#pragma once

#include "field_world.hpp"

#include <array>
#include <cstddef>

namespace wa::field {

// Stage 307: bounded, asset-free discovery log for a play session.
// The key includes area + tile position so revisits are idempotent.
// This ledger is intentionally NOT in the 40-byte world save record.
constexpr std::size_t kDiscoveryCapacity = 16;

struct FieldClue {
  int area = -1;
  int x = -1;
  int y = -1;
};

struct FieldDiscoveryJournal {
  std::array<FieldClue, kDiscoveryCapacity> entries{};
  std::size_t count = 0;
};

enum class DiscoveryResult {
  Recorded, PreviouslyRecorded, Full, Invalid
};

[[nodiscard]] inline DiscoveryResult record_discovery(
    const FieldWorld& world, FieldDiscoveryJournal& journal,
    int area, int x, int y) noexcept {
  if (!world.valid() || area < 0 || area >= kFieldAreaCount ||
      journal.count > journal.entries.size())
    return DiscoveryResult::Invalid;
  const auto& map = world.areas[static_cast<std::size_t>(area)].map;
  // Only authored event markers can be collected. Exits and ordinary
  // terrain never become clues. Validation happens before mutation.
  if (map.tile(x, y) != '!') return DiscoveryResult::Invalid;

  for (std::size_t i = 0; i < journal.count; ++i) {
    const FieldClue& previous = journal.entries[i];
    if (previous.area < 0 || previous.area >= kFieldAreaCount ||
        world.areas[static_cast<std::size_t>(previous.area)].map.tile(
            previous.x, previous.y) != '!')
      return DiscoveryResult::Invalid;
    for (std::size_t j = 0; j < i; ++j)
      if (journal.entries[j].area == previous.area &&
          journal.entries[j].x == previous.x &&
          journal.entries[j].y == previous.y)
        return DiscoveryResult::Invalid;
    if (previous.area == area && previous.x == x && previous.y == y)
      return DiscoveryResult::PreviouslyRecorded;
  }
  if (journal.count == journal.entries.size()) return DiscoveryResult::Full;
  journal.entries[journal.count++] = {area, x, y};
  return DiscoveryResult::Recorded;
}

}  // namespace wa::field
