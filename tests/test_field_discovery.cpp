#include "field_discovery.hpp"
#include "field_save_codec.hpp"

#include <cstdlib>

namespace {
using namespace wa::field;
void require(bool ok) { if (!ok) std::abort(); }

void test_distinct_events_and_revisits_are_idempotent() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal notes{};
  require(record_discovery(world,notes,0,4,1) == DiscoveryResult::Recorded);
  require(notes.count == 1);
  require(record_discovery(world,notes,0,4,1) ==
          DiscoveryResult::PreviouslyRecorded);
  require(notes.count == 1);
  require(record_discovery(world,notes,1,4,3) == DiscoveryResult::Recorded);
  require(notes.count == 2);
  require(notes.entries[0].area == 0 && notes.entries[1].area == 1);
}

void test_invalid_markers_and_corrupt_ledgers_cannot_mutate() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal notes{};
  require(record_discovery(world,notes,0,6,5) ==
          DiscoveryResult::Invalid); // Exit.
  require(record_discovery(world,notes,0,1,1) ==
          DiscoveryResult::Invalid); // Floor.
  require(record_discovery(world,notes,7,4,1) ==
          DiscoveryResult::Invalid); // Unknown area.
  require(record_discovery(world,notes,0,-1,1) ==
          DiscoveryResult::Invalid); // Bounds.
  require(notes.count == 0);
  notes.count = notes.entries.size() + 1;
  const auto invalid = notes;
  require(record_discovery(world,notes,0,4,1) ==
          DiscoveryResult::Invalid);
  require(notes.count == invalid.count);
  notes = {};
  notes.count = 1;
  notes.entries[0] = {0,0,0};
  require(record_discovery(world,notes,1,4,3) ==
          DiscoveryResult::Invalid);
  require(notes.count == 1);
}

void test_full_ledger_returns_error_without_insertion() {
  // The synthetic world has only 2 unique markers, so capacity is
  // exceeded here with deliberately invalid repeated records.
  // Malformed ledger entries must be rejected before any overflow.
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal notes{};
  notes.count = notes.entries.size();
  for (auto& item : notes.entries) item = {0,4,1};
  require(record_discovery(world,notes,1,4,3) ==
          DiscoveryResult::Invalid);
  require(notes.count == notes.entries.size());
}


void test_revisit_cannot_hide_corruption_after_matching_key() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal notes{};
  notes.count = 2;
  notes.entries[0] = {0, 4, 1}; // The requested clue matches first.
  notes.entries[1] = {1, 0, 0}; // Invalid: a wall, not an event.
  require(record_discovery(world, notes, 0, 4, 1) ==
          DiscoveryResult::Invalid);
  require(notes.count == 2 && notes.entries[0].x == 4 &&
          notes.entries[1].x == 0);
  notes.entries[1] = notes.entries[0]; // Duplicate entry later in journal.
  require(record_discovery(world, notes, 0, 4, 1) ==
          DiscoveryResult::Invalid);
  require(notes.count == 2);
  notes.entries[1] = {1, 4, 3};
  require(record_discovery(world, notes, 0, 4, 1) ==
          DiscoveryResult::PreviouslyRecorded);
  require(notes.count == 2);
}


void test_discoveries_cannot_change_version_one_save_bytes() {
  const FieldWorld world = make_demo_world();
  const WorldState saved_world = start_world(world);
  FieldSaveRecord original{};
  FieldSaveRecord after_discovery{};
  FieldDiscoveryJournal journal{};
  require(encode_field_save(world, saved_world, original) ==
          FieldSaveStatus::Encoded);
  require(original.size() == kFieldSaveRecordSize);
  require(original[4] == kFieldSaveVersion);
  require(record_discovery(world, journal, 0, 4, 1) ==
          DiscoveryResult::Recorded);
  require(record_discovery(world, journal, 1, 4, 3) ==
          DiscoveryResult::Recorded);
  require(journal.count == 2);
  require(encode_field_save(world, saved_world, after_discovery) ==
          FieldSaveStatus::Encoded);
  // A session-only journal must not leak into any v1 payload byte or CRC.
  require(original == after_discovery);
  WorldState loaded{};
  require(decode_field_save(world, original, loaded) ==
          FieldSaveStatus::Decoded);
  require(loaded.area == saved_world.area &&
          loaded.player.x == saved_world.player.x &&
          loaded.player.y == saved_world.player.y);
}
}
int main() {
  test_distinct_events_and_revisits_are_idempotent();
  test_invalid_markers_and_corrupt_ledgers_cannot_mutate();
  test_full_ledger_returns_error_without_insertion();
  test_revisit_cannot_hide_corruption_after_matching_key();
  test_discoveries_cannot_change_version_one_save_bytes();
}
