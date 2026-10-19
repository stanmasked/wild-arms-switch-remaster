#include "field_journal_view.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
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

void test_all_authored_and_fallback_note_glyphs_are_complete() {
  // Cover *every* letter of the two current original demo clues and
  // of the neutral fallback for future author-created map events.
  // An unsupported character would otherwise silently vanish.
  const FieldClue clues[]{{0, 4, 1}, {1, 4, 3}, {0, 0, 0}};
  for (const FieldClue& clue : clues) {
    const FieldClueNote note = field_clue_note(clue);
    const char* texts[]{note.title, note.detail};
    for (const char* text : texts) {
      for (const char* c = text; *c; ++c) {
        if (*c == ' ') continue;
        bool ink = false;
        for (std::uint8_t bits : journal_glyph(*c))
          if (bits != 0) ink = true;
        require(ink);
      }
    }
  }
  require(journal_glyph('F')[0] == 31 &&
          journal_glyph('F')[3] == 30);
  require(journal_glyph('B')[0] == 30 &&
          journal_glyph('B')[3] == 30);
  const FieldClueNote fallback = field_clue_note({0, 0, 0});
  Screen screen;
  draw_journal_text(screen.target, 100, 100, fallback.title);
  draw_journal_text(screen.target, 100, 124, fallback.detail);
  constexpr std::uint32_t white = rgba(246, 247, 252);
  // First character F and the B of "FIELD OBSERVATION" both render.
  require(screen.at(100, 100) == white);
  require(screen.at(100 + 7 * 14 + 2, 100) == white);
  require(screen.at(100, 124) == white); // N in "NO FIELD NOTES"
  require(screen.at(100 + 3 * 14, 124) == white); // F in detail
  screen.assert_guards();
}

void test_journal_authored_notes_glyphs_and_layout() {
  const FieldWorld world = make_demo_world();
  FieldDiscoveryJournal notes{};
  const FieldClueNote first = field_clue_note({0, 4, 1});
  const FieldClueNote second = field_clue_note({1, 4, 3});
  require(std::strcmp(first.title, "OLD RADIO NOTE") == 0);
  require(std::strcmp(first.detail, "SIGNAL IN STATIC") == 0);
  require(std::strcmp(second.title, "SILENT RELAY") == 0);
  require(std::strcmp(second.detail, "AN ECHO ANSWERS") == 0);
  require(std::strcmp(field_clue_note({0, 1, 1}).title,
                      "FIELD OBSERVATION") == 0);
  const auto& g = journal_glyph('G');
  const auto& r = journal_glyph('R');
  const auto& w = journal_glyph('W');
  require(g[3] == 23 && r[4] == 20 && w[6] == 10);
  require(record_discovery(world, notes, 0, 4, 1) ==
          DiscoveryResult::Recorded);
  Screen screen;
  require(draw_discovery_journal(screen.target, world, notes));
  const auto first_render = screen.data;
  // At x=340, each newly-authored title/detail paints visible glyphs.
  require(screen.at(340 + 2, 168) == rgba(246, 247, 252));
  require(screen.at(340 + 2, 188) == rgba(246, 247, 252));
  // Detail is an independent second line, separated from title.
  require(screen.at(340 + 2, 184) == rgba(17, 26, 40));
  require(record_discovery(world, notes, 1, 4, 3) ==
          DiscoveryResult::Recorded);
  require(draw_discovery_journal(screen.target, world, notes));
  require(first_render != screen.data);
  require(screen.at(340 + 2, 220) == rgba(246, 247, 252));
  require(screen.at(340 + 2, 240) == rgba(246, 247, 252));
  require(screen.at(340 + 2, 188) == rgba(246, 247, 252));
  screen.assert_guards();
}

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
  test_all_authored_and_fallback_note_glyphs_are_complete();
  test_journal_authored_notes_glyphs_and_layout();
  test_empty_and_recorded_views_are_distinct_and_repeatable();
  test_discovered_marker_is_read_only_area_specific_and_bounded();
  test_corruption_or_target_rejected_without_pixel_mutation();
}
