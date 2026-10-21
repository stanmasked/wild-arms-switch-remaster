#pragma once

#include "field_view.hpp"

#include <cstddef>
#include <cstdint>

namespace wa::field {

// Portable, asset-free RGBA8888 reference shared by host tests and libnx.
// Pixel layout follows libnx RGBA8: red in the least significant byte.
constexpr int kRasterWidth = 1280;
constexpr int kRasterHeight = 720;
constexpr int kRasterTileSize = 64;
constexpr int kRasterStatusHeight = 10;

[[nodiscard]] constexpr std::uint32_t rgba(
    unsigned r, unsigned g, unsigned b) noexcept {
  return (r & 255u) | ((g & 255u) << 8) |
         ((b & 255u) << 16) | (255u << 24);
}

struct PixelTarget {
  std::uint32_t* pixels = nullptr;
  int width = 0;
  int height = 0;
  int stride_pixels = 0;
};

enum class RasterOutcome { Ready, InvalidTarget, InvalidFrame, InvalidArea };

// Validation precedes ALL writes, including the clear colour. Client must
// provide a writable buffer of at least stride_pixels * height uint32_t.
[[nodiscard]] inline RasterOutcome validate_raster(
    const PixelTarget& target, const RenderFrame& frame,
    int area_index) noexcept {
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight ||
      target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192)
    return RasterOutcome::InvalidTarget;
  if (area_index != 0 && area_index != 1)
    return RasterOutcome::InvalidArea;
  if (!frame.ready || frame.width < 1 || frame.height < 1 ||
      frame.width > kMaximumViewportDimension ||
      frame.height > kMaximumViewportDimension ||
      frame.width > kRasterWidth / kRasterTileSize ||
      frame.height > kRasterHeight / kRasterTileSize ||
      !valid_facing(frame.player_facing))
    return RasterOutcome::InvalidFrame;

  int players = 0;
  for (int y = 0; y < frame.height; ++y)
    for (int x = 0; x < frame.width; ++x) {
      const RenderCell* cell = frame.at(x, y);
      if (cell == nullptr) return RasterOutcome::InvalidFrame;
      switch (cell->terrain) {
        case CellKind::Outside:
          if (cell->player) return RasterOutcome::InvalidFrame;
          break;
        case CellKind::Wall:
          if (cell->player) return RasterOutcome::InvalidFrame;
          break;
        case CellKind::Floor:
        case CellKind::Event:
        case CellKind::Exit:
          break;
        default:
          return RasterOutcome::InvalidFrame;
      }
      if (cell->player && ++players > 1)
        return RasterOutcome::InvalidFrame;
    }
  return players == 1 ? RasterOutcome::Ready : RasterOutcome::InvalidFrame;
}

inline void fill_raster_rect(const PixelTarget& target, int x, int y,
                             int w, int h, std::uint32_t colour) noexcept {
  const int x0 = x < 0 ? 0 : (x > target.width ? target.width : x);
  const int y0 = y < 0 ? 0 : (y > target.height ? target.height : y);
  const int rx = x + w;
  const int ry = y + h;
  const int x1 = rx < 0 ? 0 : (rx > target.width ? target.width : rx);
  const int y1 = ry < 0 ? 0 : (ry > target.height ? target.height : ry);
  for (int row = y0; row < y1; ++row) {
    std::uint32_t* line = target.pixels +
        static_cast<std::size_t>(row) *
        static_cast<std::size_t>(target.stride_pixels);
    for (int col = x0; col < x1; ++col)
      line[col] = colour;
  }
}

[[nodiscard]] constexpr std::uint32_t terrain_rgba(
    const CellKind kind) noexcept {
  switch (kind) {
    case CellKind::Outside: return rgba(14, 20, 34);
    case CellKind::Wall: return rgba(47, 68, 87);
    case CellKind::Floor: return rgba(174, 155, 115);
    case CellKind::Event: return rgba(245, 183, 66);
    case CellKind::Exit: return rgba(63, 191, 138);
  }
  return rgba(14, 20, 34);
}

[[nodiscard]] inline RasterOutcome draw_field_pixels(
    const PixelTarget& target, const RenderFrame& frame,
    const bool paused, const int area_index) noexcept {
  const RasterOutcome preflight = validate_raster(target, frame, area_index);
  if (preflight != RasterOutcome::Ready) return preflight;

  fill_raster_rect(target, 0, 0, kRasterWidth, kRasterHeight,
                   area_index == 0 ? rgba(14, 20, 34) :
                                     rgba(19, 34, 38));
  const int start_x = (kRasterWidth - frame.width * kRasterTileSize) / 2;
  const int start_y = (kRasterHeight - frame.height * kRasterTileSize) / 2;
  for (int y = 0; y < frame.height; ++y)
    for (int x = 0; x < frame.width; ++x) {
      const RenderCell& cell = *frame.at(x, y);
      const int left = start_x + x * kRasterTileSize;
      const int top = start_y + y * kRasterTileSize;
      fill_raster_rect(target, left + 1, top + 1,
                       kRasterTileSize - 2, kRasterTileSize - 2,
                       terrain_rgba(cell.terrain));
      if (!cell.player) continue;

      const int cx = left + kRasterTileSize / 2;
      const int cy = top + kRasterTileSize / 2;
      fill_raster_rect(target, cx - 19, cy - 19, 38, 38,
                       paused ? rgba(246, 246, 246) : rgba(201, 67, 76));
      int mx = cx - 5;
      int my = cy - 5;
      switch (frame.player_facing) {
        case Direction::Up: my -= 15; break;
        case Direction::Down: my += 15; break;
        case Direction::Left: mx -= 15; break;
        case Direction::Right: mx += 15; break;
        case Direction::None: break;
      }
      fill_raster_rect(target, mx, my, 10, 10, rgba(22, 27, 42));
    }
  fill_raster_rect(target, 0, 0, kRasterWidth, kRasterStatusHeight,
                   paused ? rgba(246, 183, 66) :
                     area_index == 0 ? rgba(63, 191, 138) :
                                       rgba(105, 160, 230));
  return RasterOutcome::Ready;
}

// A transient, asset-free inspection outline drawn inside the selected
// event/exit tile. It never touches the canonical field raster unless
// the player explicitly presses A while facing an adjacent marker.
[[nodiscard]] inline bool draw_field_inspection(
    const PixelTarget& target, const RenderFrame& frame,
    int world_x, int world_y, Trigger kind) noexcept {
  if (kind != Trigger::Event && kind != Trigger::Exit) return false;
  if (validate_raster(target, frame, 0) != RasterOutcome::Ready)
    return false;
  const int vx = world_x - frame.world_left;
  const int vy = world_y - frame.world_top;
  const RenderCell* cell = frame.at(vx, vy);
  if (!cell || cell->player ||
      cell->terrain != (kind == Trigger::Event ?
                        CellKind::Event : CellKind::Exit))
    return false;

  const int x = (kRasterWidth - frame.width * kRasterTileSize) / 2 +
                vx * kRasterTileSize + 7;
  const int y = (kRasterHeight - frame.height * kRasterTileSize) / 2 +
                vy * kRasterTileSize + 7;
  constexpr int side = kRasterTileSize - 14;
  constexpr int edge = 5;
  const std::uint32_t highlight =
      kind == Trigger::Event ? rgba(255, 247, 172) :
                               rgba(172, 255, 230);
  fill_raster_rect(target, x, y, side, edge, highlight);
  fill_raster_rect(target, x, y + side - edge, side, edge, highlight);
  fill_raster_rect(target, x, y, edge, side, highlight);
  fill_raster_rect(target, x + side - edge, y, edge, side, highlight);
  return true;
}

}  // namespace wa::field
