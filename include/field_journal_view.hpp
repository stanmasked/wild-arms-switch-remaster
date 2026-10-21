#pragma once

#include "field_discovery.hpp"
#include "field_clue_notes.hpp"
#include "field_inspection_ui.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace wa::field {

// Stage 308: read-only, asset-free manual journal overlay. L is held to
// view it; the journal remains volatile and the 40-byte save is unchanged.
constexpr int kJournalPanelX = 304;
constexpr int kJournalPanelY = 80;
constexpr int kJournalPanelWidth = 672;
constexpr int kJournalPanelHeight = 560;

// Never render untrusted/corrupt ledger entries. Validate ALL entries,
// not only the ones currently visible on the screen.
[[nodiscard]] inline bool valid_discovery_journal(
    const FieldWorld& world,
    const FieldDiscoveryJournal& journal) noexcept {
  if (!world.valid() || journal.count > journal.entries.size())
    return false;
  for (std::size_t i = 0; i < journal.count; ++i) {
    const FieldClue& clue = journal.entries[i];
    if (clue.area < 0 || clue.area >= kFieldAreaCount ||
        world.areas[static_cast<std::size_t>(clue.area)].map.tile(
            clue.x, clue.y) != '!')
      return false;
    for (std::size_t j = 0; j < i; ++j)
      if (journal.entries[j].area == clue.area &&
          journal.entries[j].x == clue.x &&
          journal.entries[j].y == clue.y)
        return false;
  }
  return true;
}

[[nodiscard]] inline std::size_t count_world_clues(
    const FieldWorld& world) noexcept {
  if (!world.valid()) return 0;
  std::size_t count = 0;
  for (const FieldArea& area : world.areas)
    for (int y = 0; y < area.map.height; ++y)
      for (int x = 0; x < area.map.width; ++x)
        if (area.map.tile(x, y) == '!') ++count;
  return count;
}

[[nodiscard]] inline const std::array<std::uint8_t, 7>&
journal_glyph(char symbol) noexcept {
  static constexpr std::array<std::uint8_t, 7> numerals[] = {
      {14,17,19,21,25,17,14}, // 0
      {4,12,4,4,4,4,14},      // 1
      {14,17,1,2,4,8,31},    // 2
      {30,1,1,14,1,1,30},    // 3
      {2,6,10,18,31,2,2},   // 4
      {31,16,16,30,1,1,30}, // 5
      {14,16,16,30,17,17,14},// 6
      {31,1,2,4,8,8,8},      // 7
      {14,17,17,14,17,17,14},// 8
      {14,17,17,15,1,1,14}  // 9
  };
  static constexpr std::array<std::uint8_t, 7> s{15,16,16,14,1,1,30};
  static constexpr std::array<std::uint8_t, 7> y{17,17,10,4,4,4,4};
  static constexpr std::array<std::uint8_t, 7> slash{1,1,2,4,8,16,16};
  // Glyphs missing from the original inspection-caption subset.
  static constexpr std::array<std::uint8_t, 7> b{30,17,17,30,17,17,30};
  static constexpr std::array<std::uint8_t, 7> f{31,16,16,30,16,16,16};
  static constexpr std::array<std::uint8_t, 7> g{14,17,16,23,17,17,14};
  static constexpr std::array<std::uint8_t, 7> r{30,17,17,30,20,18,17};
  static constexpr std::array<std::uint8_t, 7> w{17,17,17,21,21,21,10};
  if (symbol >= '0' && symbol <= '9')
    return numerals[static_cast<unsigned>(symbol - '0')];
  if (symbol == 'S') return s;
  if (symbol == 'Y') return y;
  if (symbol == '/') return slash;
  if (symbol == 'B') return b;
  if (symbol == 'F') return f;
  if (symbol == 'G') return g;
  if (symbol == 'R') return r;
  if (symbol == 'W') return w;
  return inspection_caption_glyph(symbol);
}

inline void draw_journal_text(const PixelTarget& target,
                              int x0, int y0, const char* text) noexcept {
  for (std::size_t i = 0; text[i] != '\0' && i < 32; ++i) {
    const auto& glyph = journal_glyph(text[i]);
    for (int row = 0; row < 7; ++row)
      for (int column = 0; column < 5; ++column)
        if ((glyph[static_cast<std::size_t>(row)] >>
             (4 - column)) & 1u)
          fill_raster_rect(target, x0 + static_cast<int>(i) * 14 +
                           column * 2, y0 + row * 2, 2, 2,
                           rgba(246, 247, 252));
  }
}

// A compact in-world tick marks an already-discovered event while walking.
// The marker is purely visual: it cannot rewrite a map, advance the
// discovery ledger or affect the deterministic autoplay reference frames.
// Every journal entry is preflighted before any pixel can be written.
[[nodiscard]] inline bool draw_discovered_clue_markers(
    const PixelTarget& target, const FieldWorld& world,
    const RenderFrame& frame, int area_index,
    const FieldDiscoveryJournal& journal) noexcept {
  if (!valid_discovery_journal(world, journal) ||
      validate_raster(target, frame, area_index) != RasterOutcome::Ready)
    return false;
  const int origin_x = (kRasterWidth -
                        frame.width * kRasterTileSize) / 2;
  const int origin_y = (kRasterHeight -
                        frame.height * kRasterTileSize) / 2;
  for (std::size_t i = 0; i < journal.count; ++i) {
    const FieldClue& clue = journal.entries[i];
    if (clue.area != area_index) continue;
    const int vx = clue.x - frame.world_left;
    const int vy = clue.y - frame.world_top;
    const RenderCell* cell = frame.at(vx, vy);
    // Do not paint over the player or over non-event terrain.
    if (!cell || cell->terrain != CellKind::Event || cell->player) continue;
    const int tile_x = origin_x + vx * kRasterTileSize;
    const int tile_y = origin_y + vy * kRasterTileSize;
    constexpr std::uint32_t ink = rgba(246, 247, 252);
    fill_raster_rect(target, tile_x + 25, tile_y + 25, 18, 18,
                     rgba(105, 160, 230));
    // Small white checkmark, separated from an A-inspection outline.
    fill_raster_rect(target, tile_x + 29, tile_y + 33, 4, 4, ink);
    fill_raster_rect(target, tile_x + 33, tile_y + 37, 4, 4, ink);
    fill_raster_rect(target, tile_x + 37, tile_y + 31, 4, 4, ink);
    fill_raster_rect(target, tile_x + 41, tile_y + 27, 2, 4, ink);
  }
  return true;
}

[[nodiscard]] inline bool draw_discovery_journal(
    const PixelTarget& target, const FieldWorld& world,
    const FieldDiscoveryJournal& journal) noexcept {
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight ||
      target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192) return false;
  if (!valid_discovery_journal(world, journal)) return false;

  fill_raster_rect(target, kJournalPanelX, kJournalPanelY,
                   kJournalPanelWidth, kJournalPanelHeight,
                   rgba(105, 160, 230));
  fill_raster_rect(target, kJournalPanelX + 4, kJournalPanelY + 4,
                   kJournalPanelWidth - 8, kJournalPanelHeight - 8,
                   rgba(17, 26, 40));
  char line[48]{};
  (void)std::snprintf(line, sizeof(line), "CLUES %zu/%zu",
                      journal.count, count_world_clues(world));
  draw_journal_text(target, kJournalPanelX + 36,
                    kJournalPanelY + 36, line);
  // Give the player a geographic overview in the free upper-right
  // journal header. Counts are derived from authored event tiles and
  // the validated in-session ledger; neither changes saved world state.
  // The two rows end above the first narrative-note row at y=168.
  for (int area = 0; area < kFieldAreaCount; ++area) {
    const Map& map = world.areas[static_cast<std::size_t>(area)].map;
    std::size_t total = 0;
    for (int y = 0; y < map.height; ++y)
      for (int x = 0; x < map.width; ++x)
        if (map.tile(x, y) == '!') ++total;
    std::size_t discovered = 0;
    for (std::size_t i = 0; i < journal.count; ++i)
      if (journal.entries[i].area == area) ++discovered;
    (void)std::snprintf(line, sizeof(line), "AREA %d %zu/%zu",
                        area, discovered, total);
    draw_journal_text(target, kJournalPanelX + 356,
                      kJournalPanelY + 36 + area * 24, line);
  }
  // Every one of the 16 capacity slots remains visible: eight paired
  // title/detail rows in each of two columns. No clipped or hidden clues.
  constexpr std::size_t rows_per_column = 8;
  constexpr int column_stride = 320;
  constexpr int row_stride = 52;
  for (std::size_t i = 0; i < journal.count; ++i) {
    const FieldClue& clue = journal.entries[i];
    const FieldClueNote note = field_clue_note(clue);
    const int x = kJournalPanelX + 36 +
        static_cast<int>(i / rows_per_column) * column_stride;
    const int y = kJournalPanelY + 88 +
        static_cast<int>(i % rows_per_column) * row_stride;
    (void)std::snprintf(line, sizeof(line), "A%d  %s",
                        clue.area, note.title);
    draw_journal_text(target, x, y, line);
    draw_journal_text(target, x, y + 20, note.detail);
  }
  return true;
}

} // namespace wa::field
