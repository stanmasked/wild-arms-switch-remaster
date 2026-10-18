#include "field_pixels.hpp"
#include "field_world.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {
using namespace wa::field;

constexpr std::array<const char*, 5> kNames{{
    "00_area0_start", "01_area0_event", "02_area0_exit",
    "03_area1_start", "04_area0_return"
}};

void require(bool value) {
  if (!value) std::abort();
}

void save_ppm(const std::filesystem::path& path,
              const std::vector<std::uint32_t>& pixels) {
  std::ofstream out(path, std::ios::binary);
  require(out.good());
  out << "P6\n" << kRasterWidth << ' ' << kRasterHeight << "\n255\n";
  std::vector<unsigned char> row(
      static_cast<std::size_t>(kRasterWidth) * 3u);
  for (int y = 0; y < kRasterHeight; ++y) {
    for (int x = 0; x < kRasterWidth; ++x) {
      const std::uint32_t pixel = pixels[
          static_cast<std::size_t>(y) * kRasterWidth + x];
      const std::size_t offset = static_cast<std::size_t>(x) * 3u;
      row[offset] = static_cast<unsigned char>(pixel & 0xFFu);
      row[offset + 1] = static_cast<unsigned char>((pixel >> 8) & 0xFFu);
      row[offset + 2] = static_cast<unsigned char>((pixel >> 16) & 0xFFu);
    }
    out.write(reinterpret_cast<const char*>(row.data()),
              static_cast<std::streamsize>(row.size()));
  }
  out.flush();
  require(out.good());
}

void snapshot(const FieldWorld& world, const WorldState& state,
              const bool write, const std::filesystem::path& destination,
              const char* name) {
  require(state.area == 0 || state.area == 1);
  const Map& current_map = world.areas[static_cast<std::size_t>(state.area)].map;
  RenderFrame view;
  require(build_view(view, current_map, state.player, {11, 7}) ==
          RenderOutcome::Ready);

  std::vector<std::uint32_t> pixels(
      static_cast<std::size_t>(kRasterWidth) * kRasterHeight, 0);
  const PixelTarget target{pixels.data(), kRasterWidth,
                           kRasterHeight, kRasterWidth};
  require(draw_field_pixels(target, view, state.clock.paused_for_trigger,
                            state.area) == RasterOutcome::Ready);
  const std::uint32_t expected_status =
      state.clock.paused_for_trigger ? rgba(246, 183, 66) :
      state.area == 0 ? rgba(63, 191, 138) : rgba(105, 160, 230);
  require(pixels[0] == expected_status);
  if (write) save_ppm(destination / (std::string{name} + ".ppm"), pixels);
}

void move(WorldState& world_state, const FieldWorld& world,
          const PadSample& sample, int steps,
          Trigger final_trigger = Trigger::None) {
  for (int n = 0; n < steps; ++n) {
    const WorldFrameResult frame =
        advance_world_frame(world, world_state, sample, 160);
    const Trigger expected = n == steps - 1 ? final_trigger : Trigger::None;
    require(frame.controller.movement.trigger == expected);
    require(frame.controller.movement.status ==
            (expected == Trigger::None ? TimedStatus::Moved
                                       : TimedStatus::Triggered));
    require(frame.controller.movement.successful_steps == 1);
    require(!frame.area_changed);
  }
}

void confirm(WorldState& state, const FieldWorld& world, bool should_move_area) {
  const WorldFrameResult frame =
      advance_world_frame(world, state, PadSample{.confirm = true}, 160);
  require(frame.controller.outcome == PadFrameOutcome::Acknowledged);
  require(frame.area_changed == should_move_area);
  require(!state.clock.paused_for_trigger && state.pending == Trigger::None);
}

void playback(const std::filesystem::path& destination, bool write) {
  const FieldWorld world = make_demo_world();
  require(world.valid());
  if (write) std::filesystem::create_directories(destination);
  WorldState game = start_world(world);

  snapshot(world, game, write, destination, kNames[0]);

  const PadSample right{.dpad_right = true};
  const PadSample left{.dpad_left = true};
  const PadSample down{.dpad_down = true};

  move(game, world, right, 3, Trigger::Event);
  require(game.area == 0 && game.player.x == 4 && game.player.y == 1);
  snapshot(world, game, write, destination, kNames[1]);

  confirm(game, world, false);
  move(game, world, left, 1);
  move(game, world, down, 4);
  move(game, world, right, 3, Trigger::Exit);
  require(game.area == 0 && game.player.x == 6 && game.player.y == 5);
  snapshot(world, game, write, destination, kNames[2]);

  confirm(game, world, true);
  require(game.area == 1 && game.player.x == 1 && game.player.y == 1);
  require(game.player.successful_moves == 11);
  snapshot(world, game, write, destination, kNames[3]);

  move(game, world, down, 4);
  move(game, world, right, 5, Trigger::Exit);
  require(game.area == 1 && game.player.x == 6 && game.player.y == 5);
  confirm(game, world, true);
  require(game.area == 0 && game.player.x == 1 && game.player.y == 1);
  require(game.player.successful_moves == 20);
  snapshot(world, game, write, destination, kNames[4]);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 2) return 2;
  if (argc == 2) playback(argv[1], true);
  else playback({}, false);
  std::cout << "Field replay: 5 synthetic frames, 2 area transitions, 20 moves verified\n";
}
