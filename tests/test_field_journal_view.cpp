#include "field_journal_view.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>

namespace {
using namespace wa::field;
void require(bool ok) { if (!ok) std::abort(); }

struct Screen {
  std::vector<std::uint32_t> data = std::vector<std::uint32_t>(
      static_cast<std::size_t>(kRasterWidth + 8) * kRasterHeight + 8,
      0xBADCAFEu);
  PixelTarget target{data.data(), kRasterWidth, kRasterHeight,
                     kRasterWidth + 8};
  std::uint32_t at(int x, int y) const {
    return data[static_cast<std::size_t>(y) * target.stride_pixels +
                static_cast<std::size_t>(x)];
  }
  void assert_guards() const {
    for (int y = 0; y < kRasterHeight; ++y)
      for (int x = kRasterWidth; x < target.stride_pixels; ++x)
        require(at(x, y) == 0xBADCAFEu);
    for (std::size_t i = static_cast<std::size_t>(
             target.stride_pixels) * kRasterHeight; i < data.size(); ++i)
      require(data[i] == 0xBADCAFEu);
  }
};

void test_empty_and_recorded_views_are_distinct_and_repeatable() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal journal{};
  Screen first;
  require(count_world_clues(world) == 2);
  require(valid_discovery_journal(world, journal));
  require(draw_discovery_journal(first.target, world, journal));
  require(first.at(kJournalPanelX,kJournalPanelY) == rgba(105,160,230));
  require(first.at(kJournalPanelX+4,kJournalPanelY+4) == rgba(17,26,40));
  const auto empty = first.data;
  require(record_discovery(world, journal, 0, 4, 1) ==
          DiscoveryResult::Recorded);
  require(draw_discovery_journal(first.target, world, journal));
  require(first.data != empty);
  Screen second;
  require(draw_discovery_journal(second.target, world, journal));
  // The renderer writes only the bounded panel, never padding or tail.
  for (int y = kJournalPanelY; y < kJournalPanelY + kJournalPanelHeight; ++y)
    for (int x = kJournalPanelX; x < kJournalPanelX+kJournalPanelWidth; ++x)
      require(first.at(x,y) == second.at(x,y));
  second.assert_guards();
  first.assert_guards();
  require(record_discovery(world, journal, 1, 4, 3) ==
          DiscoveryResult::Recorded);
  require(draw_discovery_journal(second.target, world, journal));
  require(journal.count == 2);
}

void test_discovered_marker_is_read_only_area_specific_and_bounded() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal journal{};
  Screen screen;
  RenderFrame view{};
  const State player{1, 1};
  require(build_view(view, world.areas[0].map, player, {11, 7}) ==
          RenderOutcome::Ready);
  require(draw_field_pixels(screen.target, view, false, 0) ==
          RasterOutcome::Ready);
  // In area 0, original event ! sits on native tile x4,y1.
  constexpr int marker_x = 288 + 4 * 64 + 25;
  constexpr int marker_y = 136 + 1 * 64 + 25;
  const std::uint32_t untouched = screen.at(marker_x, marker_y);
  require(untouched == terrain_rgba(CellKind::Event));
  const auto before = screen.data;
  require(draw_discovered_clue_markers(
      screen.target, world, view, 0, journal));
  require(screen.data == before);
  require(record_discovery(world, journal, 0, 4, 1) ==
          DiscoveryResult::Recorded);
  require(draw_discovered_clue_markers(
      screen.target, world, view, 0, journal));
  require(screen.at(marker_x, marker_y) == rgba(105, 160, 230));
  require(screen.at(marker_x + 4, marker_y + 8) ==
          rgba(246, 247, 252));
  require(journal.count == 1);

  // The same ledger does not annotate an undiscovered event in area 1.
  RenderFrame second{};
  require(build_view(second, world.areas[1].map, player, {11, 7}) ==
          RenderOutcome::Ready);
  require(draw_field_pixels(screen.target, second, false, 1) ==
          RasterOutcome::Ready);
  constexpr int second_y = 136 + 3 * 64 + 25;
  const std::uint32_t second_unmarked = screen.at(marker_x, second_y);
  require(draw_discovered_clue_markers(
      screen.target, world, second, 1, journal));
  require(screen.at(marker_x, second_y) == second_unmarked);
  require(record_discovery(world, journal, 1, 4, 3) ==
          DiscoveryResult::Recorded);
  require(draw_discovered_clue_markers(
      screen.target, world, second, 1, journal));
  require(screen.at(marker_x, second_y) == rgba(105, 160, 230));

  // Invalid/duplicated ledgers fail before a single framebuffer write.
  FieldDiscoveryJournal broken = journal;
  broken.entries[1] = broken.entries[0];
  const auto previous = screen.data;
  require(!draw_discovered_clue_markers(
      screen.target, world, second, 1, broken));
  require(screen.data == previous);
  broken.count = broken.entries.size() + 1;
  require(!draw_discovered_clue_markers(
      screen.target, world, second, 1, broken));
  require(screen.data == previous);

  // On an occupied ! tile the player must never be covered by a marker.
  State standing_on_event{4, 1};
  RenderFrame occupied{};
  require(build_view(occupied, world.areas[0].map,
                     standing_on_event, {11, 7}) == RenderOutcome::Ready);
  require(draw_field_pixels(screen.target, occupied, false, 0) ==
          RasterOutcome::Ready);
  const auto occupied_pixels = screen.data;
  require(draw_discovered_clue_markers(
      screen.target, world, occupied, 0, journal));
  require(screen.data == occupied_pixels);
  screen.assert_guards();
}

void test_corruption_or_target_rejected_without_pixel_mutation() {
  const FieldWorld world = make_demo_world();
  Screen screen;
  const auto original = screen.data;
  FieldDiscoveryJournal journal{};
  const PixelTarget null_target{nullptr, kRasterWidth, kRasterHeight,
                                kRasterWidth};
  require(!draw_discovery_journal(null_target, world, journal));
  const PixelTarget narrow{screen.data.data(), kRasterWidth, kRasterHeight,
                           kRasterWidth - 1};
  require(!draw_discovery_journal(narrow, world, journal));
  journal.count = journal.entries.size() + 1;
  require(!draw_discovery_journal(screen.target, world, journal));
  journal = {};
  journal.count = 1;
  journal.entries[0] = {0, 0, 0}; // Wall, not an event.
  require(!draw_discovery_journal(screen.target, world, journal));
  journal.entries[0] = {0, 4, 1};
  journal.count = 2;
  journal.entries[1] = journal.entries[0]; // Duplicate key.
  require(!draw_discovery_journal(screen.target, world, journal));
  journal.entries[1] = {1, -1, 4}; // Out-of-range.
  require(!draw_discovery_journal(screen.target, world, journal));
  require(screen.data == original);
  screen.assert_guards();
}
} // namespace

int main() {
  test_empty_and_recorded_views_are_distinct_and_repeatable();
  test_discovered_marker_is_read_only_area_specific_and_bounded();
  test_corruption_or_target_rejected_without_pixel_mutation();
}
