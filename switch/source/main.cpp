#include <switch.h>

#include "field.hpp"
#include "field_world.hpp"
#include "field_view.hpp"
#include "field_pixels.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace {
using namespace wa::field;

constexpr int kWidth = 1280;
constexpr int kHeight = 720;
constexpr int kTileSize = 64;
constexpr Viewport kViewport{11, 7};

std::int16_t stick_axis(const int value) noexcept {
  return static_cast<std::int16_t>(std::clamp(value, -32768, 32767));
}

PadSample read_pad(PadState& pad) noexcept {
  const u64 buttons = padGetButtons(&pad);
  const HidAnalogStickState left = padGetStickPos(&pad, 0);
  PadSample sample{};
  sample.dpad_up = (buttons & HidNpadButton_Up) != 0;
  sample.dpad_down = (buttons & HidNpadButton_Down) != 0;
  sample.dpad_left = (buttons & HidNpadButton_Left) != 0;
  sample.dpad_right = (buttons & HidNpadButton_Right) != 0;
  sample.confirm = (buttons & HidNpadButton_A) != 0;
  sample.stick_x = stick_axis(left.x);
  // libnx reports positive stick Y upwards; field contract uses +Y downwards.
  sample.stick_y = stick_axis(-static_cast<int>(left.y));
  return sample;
}


}  // namespace

int main() {
  const FieldWorld world = make_demo_world();
  if (!world.valid()) return 1;

  Framebuffer fb{};
  ::Result setup = framebufferCreate(&fb, nwindowGetDefault(), kWidth, kHeight,
                                   PIXEL_FORMAT_RGBA_8888, 2);
  if (R_FAILED(setup)) return 2;
  setup = framebufferMakeLinear(&fb);
  if (R_FAILED(setup)) {
    framebufferClose(&fb);
    return 3;
  }

  padConfigureInput(1, HidNpadStyleSet_NpadStandard);
  PadState pad{};
  padInitializeDefault(&pad);

  WorldState game = start_world(world);
  RenderFrame view{};
  const u64 tick_frequency = armGetSystemTickFreq();
  u64 previous_tick = armGetSystemTick();

  while (appletMainLoop()) {
    padUpdate(&pad);
    if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;

    const u64 current_tick = armGetSystemTick();
    const u64 elapsed_ticks = current_tick - previous_tick;
    previous_tick = current_tick;
    // A large pause (e.g. home menu) is deliberately capped: skip game time
    // rather than running thousands of catch-up moves after resuming.
    const u64 ticks_per_ms = tick_frequency / 1000;
    const u64 elapsed_ms = ticks_per_ms ? elapsed_ticks / ticks_per_ms : 0;
    const u32 delta = static_cast<u32>(std::min<u64>(
        elapsed_ms, kMaximumMovementDeltaMs));

    const WorldFrameResult result =
        advance_world_frame(world, game, read_pad(pad), delta);
    (void)result;
    const Map& current_map = world.areas[game.area].map;
    if (build_view(view, current_map, game.player, kViewport) !=
        RenderOutcome::Ready)
      break;

    u32 stride_bytes = 0;
    u32* pixels = static_cast<u32*>(framebufferBegin(&fb, &stride_bytes));
    if (!pixels) break;
    const PixelTarget output{pixels, kWidth, kHeight,
                             static_cast<int>(stride_bytes / sizeof(u32))};
    const RasterOutcome drawn = draw_field_pixels(
        output, view, game.clock.paused_for_trigger, game.area);
    framebufferEnd(&fb);
    if (drawn != RasterOutcome::Ready) break;
  }

  framebufferClose(&fb);
  return 0;
}
