#include "field_scenario.hpp"
#include "field_pixels.hpp"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <utility>
#include <vector>

namespace {
using namespace wa::field;
void check(bool value) { if (!value) std::abort(); }
void test_scenario_checkpoints_pixels_and_replay() {
  const FieldWorld world = make_demo_world();
  check(world.valid());
  ScenarioTrack a = start_field_scenario(world);
  ScenarioTrack b = start_field_scenario(world);
  check(matches_checkpoint(a.world, 0));
  std::array<std::vector<std::uint32_t>, 5> pixels;
  const auto take = [&](int id, const WorldState& s) {
    check(matches_checkpoint(s, id));
    RenderFrame view;
    check(build_view(view, world.areas[s.area].map, s.player,
                     Viewport{11, 7}) == RenderOutcome::Ready);
    std::vector<std::uint32_t> image(
        static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
    check(draw_field_pixels({image.data(), kRasterWidth, kRasterHeight,
                            kRasterWidth}, view,
                            s.clock.paused_for_trigger, s.area) ==
          RasterOutcome::Ready);
    pixels[static_cast<std::size_t>(id)] = std::move(image);
  };
  take(0, a.world);
  int next = 1;
  for (int i=0; i<23; ++i) {
    const auto ra = advance_field_scenario(world, a);
    const auto rb = advance_field_scenario(world, b);
    check(ra.status == rb.status && ra.checkpoint == rb.checkpoint);
    check(ra.status != ScenarioStatus::Invalid &&
          ra.status != ScenarioStatus::Finished);
    check(a.world.area == b.world.area &&
          a.world.player.x == b.world.player.x &&
          a.world.player.y == b.world.player.y &&
          a.world.player.successful_moves == b.world.player.successful_moves &&
          a.world.pending == b.world.pending);
    if (ra.status == ScenarioStatus::Checkpoint) {
      check(ra.checkpoint == next++);
      take(ra.checkpoint, a.world);
    }
  }
  check(next == 5 && a.complete && b.complete);
  check(advance_field_scenario(world,a).status == ScenarioStatus::Finished);
  check(pixels[0] == pixels[4]);
  for (int i = 1; i < 4; ++i) check(pixels[i] != pixels[0]);
  check(pixels[1] != pixels[2] && pixels[2] != pixels[3]);
}
void test_invalid_data_is_rejected() {
  FieldWorld world = make_demo_world();
  ScenarioTrack good = start_field_scenario(world);
  world.areas[1].entrance_x = 0;
  check(advance_field_scenario(world, good).status == ScenarioStatus::Invalid);
  check(good.invalid && good.world.area == 0 &&
        good.world.player.x == 1);
  check(advance_field_scenario(world, good).status == ScenarioStatus::Invalid);
  check(start_field_scenario(world).invalid);
  world = make_demo_world();
  world.areas[0].entrance_x = 2;
  check(start_field_scenario(world).invalid);
}
} // namespace
int main() {
  test_scenario_checkpoints_pixels_and_replay();
  test_invalid_data_is_rejected();
}
