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
  std::vector<std::uint32_t> buffer = std::vector<std::uint32_t>(
      static_cast<std::size_t>(kRasterWidth + 8) * kRasterHeight + 16,
      0xBADCAFEu);
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


void test_quicksave_restore_manual_mode_and_autoplay_isolation() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface image;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  require(advance_field_runtime(world, rt, 0, {}, image.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeControls load_empty{{},false,false,false,true};
  const auto empty = advance_field_runtime(world, rt, step, load_empty, image.target);
  require(empty.status == RuntimeStatus::Rendered && empty.snapshot_empty);
  require(!rt.quicksave.occupied && rt.manual.player.x == 1);

  const RuntimeControls right{PadSample{.dpad_right = true}};
  require(advance_field_runtime(world,rt,step*2,right,image.target).status ==
          RuntimeStatus::Rendered);
  require(rt.manual.player.x == 2 && rt.manual.player.successful_moves == 1);
  const RuntimeControls save{PadSample{.dpad_right = true},false,false,true,false};
  const auto captured = advance_field_runtime(
      world,rt,step*3,save,image.target);
  require(captured.snapshot_stored && rt.quicksave.occupied);
  require(rt.manual.player.x == 2);
  (void)advance_field_runtime(world,rt,step*4,right,image.target);
  require(rt.manual.player.x == 3 && rt.manual.player.successful_moves == 2);
  const auto loaded = advance_field_runtime(
      world,rt,step*5,load_empty,image.target);
  require(loaded.status == RuntimeStatus::Rendered && loaded.snapshot_restored);
  require(rt.manual.player.x == 2 && rt.manual.player.successful_moves == 1);
  (void)advance_field_runtime(world,rt,step*6,right,image.target);
  require(rt.manual.player.x == 3);

  const RuntimeControls both{{},false,false,true,true};
  const WorldState before = rt.manual;
  const auto invalid = advance_field_runtime(world,rt,step*7,both,image.target);
  require(invalid.status == RuntimeStatus::InvalidSimulation);
  require(rt.manual.player.x == before.player.x &&
          rt.manual.player.successful_moves == before.player.successful_moves);

  const RuntimeControls start{{},true,false};
  const auto demo = advance_field_runtime(world,rt,step*8,start,image.target);
  require(demo.status == RuntimeStatus::Rendered && rt.autoplay);
  const auto ignored = advance_field_runtime(world,rt,step*9,save,image.target);
  require(ignored.status == RuntimeStatus::Rendered &&
          !ignored.snapshot_stored && rt.quicksave.world.player.x == 2);
  const RuntimeControls cancel{{},false,true};
  require(advance_field_runtime(world,rt,step*10,cancel,image.target).status ==
          RuntimeStatus::Rendered);
  require(!rt.autoplay && rt.manual.player.x == 1);
  const auto resume = advance_field_runtime(
      world,rt,step*11,load_empty,image.target);
  require(resume.snapshot_restored && rt.manual.player.x == 2);
  image.assert_guards();
}

void test_quicksave_pending_event_restores_pause_and_status() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface image;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  (void)advance_field_runtime(world,rt,0,{},image.target);
  const RuntimeControls right{PadSample{.dpad_right = true}};
  for (int i=1;i<=3;++i)
    require(advance_field_runtime(world,rt,step*i,right,image.target).status ==
            RuntimeStatus::Rendered);
  require(rt.manual.pending == Trigger::Event && rt.manual.player.x == 4);
  const RuntimeControls save{{},false,false,true,false};
  require(advance_field_runtime(world,rt,step*4,save,image.target).snapshot_stored);
  require(rt.quicksave.world.pending == Trigger::Event);
  const RuntimeControls confirm{PadSample{.confirm = true}};
  (void)advance_field_runtime(world,rt,step*5,confirm,image.target);
  require(rt.manual.pending == Trigger::None);
  const RuntimeControls load{{},false,false,false,true};
  require(advance_field_runtime(world,rt,step*6,load,image.target).snapshot_restored);
  require(rt.manual.pending == Trigger::Event &&
          rt.manual.clock.paused_for_trigger &&
          image.pixel(0,0) == rgba(246,183,66));
  (void)advance_field_runtime(world,rt,step*7,confirm,image.target);
  require(rt.manual.pending == Trigger::None && rt.manual.player.x == 4);
}
} // namespace
int main() {
  test_sixty_hz_manual_event_pause_and_acknowledgment();
  test_invalid_input_is_transactional_and_guarded();
  test_autoplay_timing_checkpoints_and_manual_cancel();
  test_quicksave_restore_manual_mode_and_autoplay_isolation();
  test_quicksave_pending_event_restores_pause_and_status();
}
