#include "field_pixels.hpp"
#include "field_world.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>

namespace {
using namespace wa::field;

constexpr std::uint32_t kGuard = 0xDEADBEEFu;
constexpr int kStride = kRasterWidth + 16;

void require(bool condition) {
  if (!condition) std::abort();
}

struct RasterFixture {
  std::vector<std::uint32_t> memory;
  PixelTarget target{};

  RasterFixture() : memory(static_cast<std::size_t>(kStride) *
                               kRasterHeight + 32, kGuard) {
    target = {memory.data(), kRasterWidth, kRasterHeight, kStride};
  }

  std::uint32_t pixel(int x, int y) const {
    return memory[static_cast<std::size_t>(y) * kStride +
                  static_cast<std::size_t>(x)];
  }

  void guard_intact() const {
    for (int y = 0; y < kRasterHeight; ++y)
      for (int x = kRasterWidth; x < kStride; ++x)
        require(pixel(x, y) == kGuard);
    for (std::size_t i = static_cast<std::size_t>(kStride) * kRasterHeight;
         i < memory.size(); ++i)
      require(memory[i] == kGuard);
  }
};

RenderFrame frame_for(const FieldWorld& world, const WorldState& state) {
  RenderFrame f;
  require(build_view(f, world.areas[state.area].map, state.player,
                     Viewport{11, 7}) == RenderOutcome::Ready);
  return f;
}

void test_expected_terrain_player_and_facing_pixels() {
  const FieldWorld world = make_demo_world();
  require(world.valid());
  WorldState state = start_world(world);
  const RenderFrame frame = frame_for(world, state);
  RasterFixture target;
  require(draw_field_pixels(target.target, frame, false, 0) ==
          RasterOutcome::Ready);
  const int sx = (kRasterWidth - 11 * kRasterTileSize) / 2;
  const int sy = (kRasterHeight - 7 * kRasterTileSize) / 2;

  require(target.pixel(0, 0) == rgba(63, 191, 138)); // top bar
  require(target.pixel(0, 100) == rgba(14, 20, 34)); // outside map
  require(target.pixel(sx + 10, sy + 10) ==
          terrain_rgba(CellKind::Wall));
  require(target.pixel(sx + 2 * 64 + 10, sy + 64 + 10) ==
          terrain_rgba(CellKind::Floor));
  require(target.pixel(sx + 4 * 64 + 10, sy + 64 + 10) ==
          terrain_rgba(CellKind::Event));
  require(target.pixel(sx + 6 * 64 + 10, sy + 5 * 64 + 10) ==
          terrain_rgba(CellKind::Exit));
  const int cx = sx + 64 + 32;
  const int cy = sy + 64 + 32;
  require(target.pixel(cx, cy) == rgba(201, 67, 76));
  require(target.pixel(cx, cy + 15) == rgba(22, 27, 42));
  target.guard_intact();
}

void test_area_event_and_facing_differences() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  RasterFixture first, second, paused;
  RenderFrame frame = frame_for(world, state);
  require(draw_field_pixels(first.target, frame, false, 0) ==
          RasterOutcome::Ready);
  require(draw_field_pixels(second.target, frame, false, 1) ==
          RasterOutcome::Ready);
  require(draw_field_pixels(paused.target, frame, true, 0) ==
          RasterOutcome::Ready);
  require(first.pixel(0, 100) != second.pixel(0, 100));
  require(first.pixel(0, 0) != second.pixel(0, 0));
  require(paused.pixel(0, 0) == rgba(246, 183, 66));

  state.player.facing = Direction::Left;
  frame = frame_for(world, state);
  RasterFixture left;
  require(draw_field_pixels(left.target, frame, false, 0) ==
          RasterOutcome::Ready);
  const int sx = (kRasterWidth - 11 * 64) / 2;
  const int sy = (kRasterHeight - 7 * 64) / 2;
  const int cx = sx + 96, cy = sy + 96;
  require(left.pixel(cx - 15, cy) == rgba(22, 27, 42));
  require(left.pixel(cx, cy + 15) == rgba(201, 67, 76));
}

void test_invalid_parameters_never_write() {
  const FieldWorld world = make_demo_world();
  const WorldState state = start_world(world);
  const RenderFrame correct = frame_for(world, state);
  RasterFixture fixture;
  const auto initial = fixture.memory;
  require(draw_field_pixels({nullptr, kRasterWidth, kRasterHeight, kStride},
                            correct, false, 0) ==
          RasterOutcome::InvalidTarget);
  require(draw_field_pixels({fixture.memory.data(), kRasterWidth,
                             kRasterHeight, kRasterWidth - 1},
                            correct, false, 0) ==
          RasterOutcome::InvalidTarget);
  require(draw_field_pixels(fixture.target, correct, false, 2) ==
          RasterOutcome::InvalidArea);
  RenderFrame broken = correct;
  broken.ready = false;
  require(draw_field_pixels(fixture.target, broken, false, 0) ==
          RasterOutcome::InvalidFrame);
  broken = correct;
  broken.cells[0].player = true;  // Wall cell cannot hold player.
  require(draw_field_pixels(fixture.target, broken, false, 0) ==
          RasterOutcome::InvalidFrame);
  broken = correct;
  broken.cells[0].terrain = static_cast<CellKind>(255);
  require(draw_field_pixels(fixture.target, broken, false, 0) ==
          RasterOutcome::InvalidFrame);
  broken = correct;
  broken.width = 21;  // Overflows the bounded 1280-wide canvas.
  require(draw_field_pixels(fixture.target, broken, false, 0) ==
          RasterOutcome::InvalidFrame);
  require(fixture.memory == initial);
}

void test_deterministic_frame_and_padding() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  state.player.x = 3;
  state.player.y = 1;
  state.player.facing = Direction::Up;
  RasterFixture a, b;
  const RenderFrame frame = frame_for(world, state);
  require(draw_field_pixels(a.target, frame, true, 0) ==
          RasterOutcome::Ready);
  require(draw_field_pixels(b.target, frame, true, 0) ==
          RasterOutcome::Ready);
  require(a.memory == b.memory);
  a.guard_intact();
  b.guard_intact();
}

}  // namespace

int main() {
  test_expected_terrain_player_and_facing_pixels();
  test_area_event_and_facing_differences();
  test_invalid_parameters_never_write();
  test_deterministic_frame_and_padding();
}
