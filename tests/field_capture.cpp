#include "field_pixels.hpp"
#include "field_runtime.hpp"

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

constexpr std::uint64_t kReferenceTickHz = 19200000;

// Verify that the runtime's output is the direct map+view+pixels reference,
// rather than blindly trusting both replay streams to take the same path.
void snapshot(const FieldWorld& world, const FieldRuntime& runtime,
              const std::vector<std::uint32_t>& pixels,
              const bool write, const std::filesystem::path& destination,
              const char* name, const int checkpoint) {
  const WorldState& state = runtime.demo.scenario.world;
  require(runtime.autoplay && matches_checkpoint(state, checkpoint));
  require(runtime.view.ready &&
          runtime.view.width == 11 && runtime.view.height == 7);
  const std::uint32_t expected_bar =
      state.clock.paused_for_trigger ? rgba(246, 183, 66) :
      state.area == 0 ? rgba(63, 191, 138) : rgba(105, 160, 230);
  require(!pixels.empty() && pixels[0] == expected_bar);

  const Map& current_map = world.areas[static_cast<std::size_t>(state.area)].map;
  RenderFrame independent_view{};
  require(build_view(independent_view, current_map, state.player, {11, 7}) ==
          RenderOutcome::Ready);
  require(independent_view.world_left == runtime.view.world_left &&
          independent_view.world_top == runtime.view.world_top);

  std::vector<std::uint32_t> direct(pixels.size(), 0);
  const PixelTarget surface{direct.data(), kRasterWidth,
                            kRasterHeight, kRasterWidth};
  require(draw_field_pixels(surface, independent_view,
                            state.clock.paused_for_trigger,
                            state.area) == RasterOutcome::Ready);
  require(pixels == direct);
  if (write)
    save_ppm(destination / (std::string{name} + ".ppm"), pixels);
}

void playback(const std::filesystem::path& destination, bool write) {
  const FieldWorld world = make_demo_world();
  require(world.valid());
  if (write) std::filesystem::create_directories(destination);

  std::vector<std::uint32_t> pixels(
      static_cast<std::size_t>(kRasterWidth) * kRasterHeight, 0);
  const PixelTarget surface{pixels.data(), kRasterWidth,
                            kRasterHeight, kRasterWidth};
  FieldRuntime runtime = start_field_runtime(world, kReferenceTickHz, 0);
  require(runtime.timer.valid());

  const RuntimeControls start{{}, true, false};
  const RuntimeFrame initial =
      advance_field_runtime(world, runtime, 0, start, surface);
  require(initial.status == RuntimeStatus::Rendered &&
          initial.autoplay && initial.checkpoint == -1);
  require(runtime.demo.wait_ms == kAutoplayCheckpointHoldMs);
  snapshot(world, runtime, pixels, write, destination, kNames[0], 0);

  // An independent scenario oracle proves each logical step is the same
  // even though the on-screen clock holds some frames for 2500ms.
  ScenarioTrack oracle = start_field_scenario(world);
  std::size_t prior_segment = runtime.demo.scenario.segment;
  std::uint8_t prior_repetition = runtime.demo.scenario.repetition;
  int ticks = 0;
  int next_checkpoint = 1;
  int draw_frames = 0;
  std::uint64_t clock_ticks = 0;
  while (!runtime.demo.scenario.complete) {
    require(++draw_frames < 100);
    clock_ticks += kReferenceTickHz;
    const RuntimeFrame result =
        advance_field_runtime(world, runtime, clock_ticks, {}, surface);
    require(result.status == RuntimeStatus::Rendered && result.autoplay);
    require(result.tick_status == FrameTickStatus::Ready &&
            result.delta_ms == 1000);

    const ScenarioTrack& current = runtime.demo.scenario;
    const bool progressed = current.segment != prior_segment ||
                            current.repetition != prior_repetition;
    if (progressed) {
      require(++ticks <= 23);
      const ScenarioResult step = advance_field_scenario(world, oracle);
      require(step.status != ScenarioStatus::Invalid &&
              step.status != ScenarioStatus::Finished);
      require(result.checkpoint == step.checkpoint);
      require(current.world.area == oracle.world.area &&
              current.world.player.x == oracle.world.player.x &&
              current.world.player.y == oracle.world.player.y &&
              current.world.player.facing == oracle.world.player.facing &&
              current.world.player.successful_moves ==
                  oracle.world.player.successful_moves &&
              current.world.pending == oracle.world.pending);
    } else {
      require(result.checkpoint == -1);
    }
    prior_segment = current.segment;
    prior_repetition = current.repetition;

    if (result.checkpoint >= 0) {
      require(result.checkpoint == next_checkpoint);
      snapshot(world, runtime, pixels, write, destination,
               kNames[static_cast<std::size_t>(next_checkpoint)],
               next_checkpoint);
      ++next_checkpoint;
    }
  }
  require(ticks == 23 && next_checkpoint == 5 && oracle.complete);
  require(matches_checkpoint(runtime.demo.scenario.world, 4));
  require(runtime.demo.scenario.world.player.successful_moves == 20);

  // A completed NRO demonstration freezes, rather than overwriting
  // the last reference or accidentally restarting a new movement trace.
  const auto final_frame = pixels;
  clock_ticks += kReferenceTickHz;
  const RuntimeFrame frozen = advance_field_runtime(
      world, runtime, clock_ticks, {}, surface);
  require(frozen.status == RuntimeStatus::Rendered &&
          frozen.checkpoint == -1 && pixels == final_frame);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc > 2) return 2;
  if (argc == 2) playback(argv[1], true);
  else playback({}, false);
  std::cout << "Field replay: 5 synthetic frames, 2 area transitions, 20 moves verified\n";
}
