#include "field_runtime.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>

namespace {
using namespace wa::field;
constexpr std::uint64_t kSwitchTicksPerSecond = 19200000;
constexpr std::uint64_t kSixtyFpsTicks = 320000;

void require(bool good) { if (!good) std::abort(); }

struct Surface {
  std::vector<std::uint32_t> buffer{
      static_cast<std::size_t>(kRasterWidth + 8) * kRasterHeight + 16,
      0xBADCAFEu};
  PixelTarget target{buffer.data(), kRasterWidth, kRasterHeight,
                     kRasterWidth + 8};

  [[nodiscard]] std::uint32_t pixel(int x, int y) const {
    return buffer[static_cast<std::size_t>(y) * target.stride_pixels +
                  static_cast<std::size_t>(x)];
  }
  void assert_guards() const {
    for (int y = 0; y < kRasterHeight; ++y)
      for (int x = kRasterWidth; x < target.stride_pixels; ++x)
        require(pixel(x,y) == 0xBADCAFEu);
    for (std::size_t i =
             static_cast<std::size_t>(target.stride_pixels) * kRasterHeight;
         i < buffer.size(); ++i)
      require(buffer[i] == 0xBADCAFEu);
  }
};

void test_sixty_hz_manual_event_pause_and_acknowledgment() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface image;
  require(advance_field_runtime(world, rt, 0, {}, image.target).status ==
          RuntimeStatus::Rendered);
  require(image.pixel(0,0) == rgba(63,191,138));
  require(rt.manual.player.x == 1);

  const RuntimeControls right{PadSample{.dpad_right=true}};
  for (int i=1; i<=30; ++i) {
    const auto result = advance_field_runtime(
        world, rt, kSixtyFpsTicks * i, right, image.target);
    require(result.status == RuntimeStatus::Rendered);
    require(result.delta_ms == (i % 3 == 0 ? 17u : 16u) ||
            result.delta_ms == (i % 3 == 0 ? 16u : 17u));
  }
  require(rt.manual.player.x == 4 && rt.manual.player.y == 1 &&
          rt.manual.player.successful_moves == 3 &&
          rt.manual.pending == Trigger::Event);
  require(image.pixel(0,0) == rgba(246,183,66));
  image.assert_guards();

  const RuntimeControls ack{PadSample{.confirm=true}};
  auto acknowledged = advance_field_runtime(
      world, rt, kSixtyFpsTicks * 31, ack, image.target);
  require(acknowledged.status == RuntimeStatus::Rendered);
  require(acknowledged.movement_status == TimedStatus::Idle);
  require(rt.manual.pending == Trigger::None && rt.manual.player.x == 4 &&
          rt.manual.player.successful_moves == 3);
  require(image.pixel(0,0) == rgba(63,191,138));

  for (int i=32; i<=42; ++i) {
    const auto still_held = advance_field_runtime(
        world, rt, kSixtyFpsTicks * i, ack, image.target);
    require(still_held.status == RuntimeStatus::Rendered);
  }
  require(rt.manual.player.successful_moves == 3);
  const auto pause = advance_field_runtime(
      world, rt, kSwitchTicksPerSecond * 6, right, image.target);
  require(pause.status == RuntimeStatus::Rendered);
  require(pause.tick_status == FrameTickStatus::SkippedPause &&
          pause.delta_ms == 0 && rt.manual.player.x == 4);
  image.assert_guards();
}

void test_invalid_input_is_transactional_and_guarded() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 7);
  Surface image;
  const auto original = image.buffer;
  const PixelTarget bad{nullptr,kRasterWidth,kRasterHeight,kRasterWidth};
  require(advance_field_runtime(world,rt,900000,{},bad).status ==
          RuntimeStatus::InvalidTarget);
  require(rt.timer.previous_tick == 7 && image.buffer == original);
  const FieldWorld empty{};
  require(advance_field_runtime(empty,rt,900000,{},image.target).status ==
          RuntimeStatus::InvalidWorld);
  require(rt.timer.previous_tick == 7 && image.buffer == original);
  rt.timer.frequency_hz = 1;
  require(advance_field_runtime(world,rt,900000,{},image.target).status ==
          RuntimeStatus::InvalidClock);
  require(rt.timer.previous_tick == 7 && image.buffer == original);
}

void test_autoplay_timing_checkpoints_and_manual_cancel() {
  const FieldWorld world = make_demo_world();
  FieldRuntime a = start_field_runtime(world,kSwitchTicksPerSecond,0);
  FieldRuntime b = start_field_runtime(world,kSwitchTicksPerSecond,0);
  Surface ia, ib;
  const RuntimeControls start{{},true,false};
  auto firstA = advance_field_runtime(world,a,0,start,ia.target);
  auto firstB = advance_field_runtime(world,b,0,start,ib.target);
  require(firstA.status == RuntimeStatus::Rendered &&
          firstB.status == RuntimeStatus::Rendered);
  require(a.autoplay && b.autoplay && a.demo.wait_ms == 2500);
  const auto initial = ia.buffer;
  int next_cp = 1;
  std::uint64_t ticks = 0;
  for (int i=0; i<100 && !a.demo.scenario.complete; ++i) {
    ticks += kSwitchTicksPerSecond;
    const auto ra = advance_field_runtime(world,a,ticks,{},ia.target);
    const auto rb = advance_field_runtime(world,b,ticks,{},ib.target);
    require(ra.status == RuntimeStatus::Rendered &&
            rb.status == RuntimeStatus::Rendered &&
            ra.checkpoint == rb.checkpoint &&
            ia.buffer == ib.buffer);
    require(a.demo.scenario.world.player.successful_moves <= 20);
    if (ra.checkpoint >= 0) {
      require(ra.checkpoint == next_cp++);
      require(matches_checkpoint(a.demo.scenario.world,ra.checkpoint));
      const std::uint32_t bar =
          ra.checkpoint == 1 || ra.checkpoint == 2 ?
              rgba(246,183,66) : ra.checkpoint == 3 ?
              rgba(105,160,230) : rgba(63,191,138);
      require(ia.pixel(0,0) == bar);
    }
  }
  require(a.demo.scenario.complete && b.demo.scenario.complete &&
          next_cp == 5 && ia.buffer == initial);
  require(a.demo.scenario.world.player.successful_moves == 20);
  const auto last = advance_field_runtime(
      world,a,ticks + kSwitchTicksPerSecond,{},ia.target);
  require(last.status == RuntimeStatus::Rendered &&
          a.demo.scenario.complete && ia.buffer == initial);
  const auto cancel = advance_field_runtime(
      world,a,ticks + kSwitchTicksPerSecond*2,{{},false,true},ia.target);
  require(cancel.status == RuntimeStatus::Rendered && !a.autoplay);
  require(a.manual.player.x == 1 && a.manual.player.y == 1 &&
          a.manual.player.successful_moves == 0);
  const auto restart = advance_field_runtime(
      world,a,ticks + kSwitchTicksPerSecond*3,start,ia.target);
  require(restart.status == RuntimeStatus::Rendered && a.autoplay &&
          a.demo.wait_ms == 2500 && ia.buffer == initial);
  ia.assert_guards();
  ib.assert_guards();
}

} // namespace
int main() {
  test_sixty_hz_manual_event_pause_and_acknowledgment();
  test_invalid_input_is_transactional_and_guarded();
  test_autoplay_timing_checkpoints_and_manual_cancel();
}
