#pragma once

#include "field.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {

// Host-side rendering contract: cell descriptors, not pixels or game assets.
// A future GPU backend can map CellKind to its own sprites and materials.
constexpr int kMaximumViewportDimension = 32;
constexpr std::size_t kMaximumViewportCells =
    static_cast<std::size_t>(kMaximumViewportDimension) *
    static_cast<std::size_t>(kMaximumViewportDimension);

enum class CellKind : std::uint8_t { Outside, Wall, Floor, Event, Exit };

struct RenderCell {
  CellKind terrain = CellKind::Outside;
  bool player = false;
};

struct Viewport {
  int width = 9;
  int height = 5;

  [[nodiscard]] constexpr bool valid() const noexcept {
    return width > 0 && height > 0 &&
           width <= kMaximumViewportDimension &&
           height <= kMaximumViewportDimension;
  }
};

struct RenderFrame {
  int width = 0;
  int height = 0;
  int world_left = 0;
  int world_top = 0;
  Direction player_facing = Direction::Down;
  bool ready = false;
  std::array<RenderCell, kMaximumViewportCells> cells{};

  [[nodiscard]] const RenderCell* at(int x, int y) const noexcept {
    if (!ready || width <= 0 || height <= 0 ||
        width > kMaximumViewportDimension ||
        height > kMaximumViewportDimension ||
        x < 0 || y < 0 || x >= width || y >= height)
      return nullptr;
    return &cells[static_cast<std::size_t>(y) *
                      static_cast<std::size_t>(width) +
                  static_cast<std::size_t>(x)];
  }
};

enum class RenderOutcome { Ready, InvalidViewport, InvalidMap, InvalidState };

[[nodiscard]] constexpr bool valid_facing(Direction d) noexcept {
  switch (d) {
    case Direction::None:
    case Direction::Up:
    case Direction::Down:
    case Direction::Left:
    case Direction::Right:
      return true;
  }
  return false;
}

[[nodiscard]] constexpr CellKind cell_kind(char tile) noexcept {
  switch (tile) {
    case '#': return CellKind::Wall;
    case '.': return CellKind::Floor;
    case '!': return CellKind::Event;
    case 'E': return CellKind::Exit;
    default: return CellKind::Outside;
  }
}

[[nodiscard]] constexpr int camera_origin(int player, int map_size,
                                          int view_size) noexcept {
  if (map_size < view_size)
    return -(view_size - map_size) / 2;  // Center a small map with padding.
  const int desired = player - view_size / 2;
  if (desired < 0) return 0;
  const int limit = map_size - view_size;
  return desired > limit ? limit : desired;
}

// Transactional output: any invalid parameter leaves the previous frame
// unchanged. Rendering reads gameplay state, it never changes gameplay state.
[[nodiscard]] inline RenderOutcome build_view(
    RenderFrame& out, const Map& map, const State& player,
    Viewport viewport) noexcept {
  if (!viewport.valid()) return RenderOutcome::InvalidViewport;
  if (!map.valid()) return RenderOutcome::InvalidMap;
  if (player.x < 0 || player.y < 0 ||
      player.x >= map.width || player.y >= map.height ||
      !valid_facing(player.facing) ||
      map.tiles[static_cast<std::size_t>(player.y) *
                    static_cast<std::size_t>(map.width) +
                static_cast<std::size_t>(player.x)] == '#')
    return RenderOutcome::InvalidState;

  RenderFrame next{};
  next.width = viewport.width;
  next.height = viewport.height;
  next.world_left = camera_origin(player.x, map.width, viewport.width);
  next.world_top = camera_origin(player.y, map.height, viewport.height);
  next.player_facing = player.facing;
  next.ready = true;

  for (int sy = 0; sy < viewport.height; ++sy) {
    const int wy = next.world_top + sy;
    for (int sx = 0; sx < viewport.width; ++sx) {
      const int wx = next.world_left + sx;
      RenderCell& target =
          next.cells[static_cast<std::size_t>(sy) *
                         static_cast<std::size_t>(viewport.width) +
                     static_cast<std::size_t>(sx)];
      if (wx >= 0 && wy >= 0 && wx < map.width && wy < map.height) {
        const char tile =
            map.tiles[static_cast<std::size_t>(wy) *
                          static_cast<std::size_t>(map.width) +
                      static_cast<std::size_t>(wx)];
        target.terrain = cell_kind(tile);
        target.player = wx == player.x && wy == player.y;
      }
    }
  }
  out = next;
  return RenderOutcome::Ready;
}

// Optional ASCII adapter for the host demo, not the graphics backend.
[[nodiscard]] constexpr char glyph_for(const RenderCell& cell,
                                        Direction facing) noexcept {
  if (cell.player) {
    switch (facing) {
      case Direction::Up: return '^';
      case Direction::Down: return 'v';
      case Direction::Left: return '<';
      case Direction::Right: return '>';
      case Direction::None: return '@';
    }
    return '?';
  }
  switch (cell.terrain) {
    case CellKind::Outside: return ' ';
    case CellKind::Wall: return '#';
    case CellKind::Floor: return '.';
    case CellKind::Event: return '!';
    case CellKind::Exit: return 'E';
  }
  return '?';
}

}  // namespace wa::field
