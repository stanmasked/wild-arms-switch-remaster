#include "field_pixels.hpp"
#include "field_scenario.hpp"

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

void playback(const std::filesystem::path& destination, bool write) {
  const FieldWorld world = make_demo_world();
  require(world.valid());
  if (write) std::filesystem::create_directories(destination);
  ScenarioTrack scenario = start_field_scenario(world);
  require(!scenario.invalid);
  snapshot(world, scenario.world, write, destination, kNames[0]);
  int next_checkpoint = 1;
  int ticks = 0;
  while (!scenario.complete) {
    require(ticks < 23);
    const ScenarioResult step = advance_field_scenario(world, scenario);
    require(step.status != ScenarioStatus::Invalid &&
            step.status != ScenarioStatus::Finished);
    if (step.status == ScenarioStatus::Checkpoint) {
      require(step.checkpoint == next_checkpoint);
      snapshot(world, scenario.world, write, destination,
               kNames[static_cast<std::size_t>(next_checkpoint)]);
      ++next_checkpoint;
    }
    ++ticks;
  }
  require(ticks == 23 && next_checkpoint == 5);
  require(matches_checkpoint(scenario.world, 4));
  require(advance_field_scenario(world, scenario).status ==
          ScenarioStatus::Finished);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 2) return 2;
  if (argc == 2) playback(argv[1], true);
  else playback({}, false);
  std::cout << "Field replay: 5 synthetic frames, 2 area transitions, 20 moves verified\n";
}
