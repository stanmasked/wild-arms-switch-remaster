#include <switch.h>

#include "field.hpp"
#include "field_world.hpp"
#include "field_view.hpp"
#include "field_pixels.hpp"
#include "field_scenario.hpp"
#include "field_autoplay.hpp"
#include "field_frame_ticks.hpp"

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
  AutoplayTrack demo = start_field_autoplay(world);
  bool autoplay = false;
  RenderFrame view{};
  FrameTickClock frame_clock =
      make_frame_tick_clock(armGetSystemTickFreq(), armGetSystemTick());
  if (!frame_clock.valid()) {
    framebufferClose(&fb);
    return 4;
  }

  while (appletMainLoop()) {
    padUpdate(&pad);
    if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;

    const FrameTickDelta frame_time =
        advance_frame_ticks(frame_clock, armGetSystemTick());
    if (frame_time.status == FrameTickStatus::InvalidClock) break;
    // Counter resets and long applet pauses deliberately advance no game
    // time; fractional milliseconds are retained for normal display frames.
    const u32 delta = frame_time.milliseconds;

    const u64 pressed = padGetButtonsDown(&pad);
    if (pressed & HidNpadButton_X) {
      demo = start_field_autoplay(world);
      if (demo.failed) break;
      autoplay = true;
    } else if (autoplay && (pressed & HidNpadButton_B)) {
      autoplay = false;
      game = start_world(world);
    }

    if (autoplay) {
      const AutoplayFrame tick = advance_field_autoplay(world, demo, delta);
      if (tick.status == AutoplayStatus::Invalid ||
          tick.status == AutoplayStatus::InvalidDelta)
        break;
    } else {
      const WorldFrameResult manual =
          advance_world_frame(world, game, read_pad(pad), delta);
      (void)manual;
    }
    const WorldState& displayed = autoplay ? demo.scenario.world : game;
    const Map& current_map = world.areas[displayed.area].map;
    if (build_view(view, current_map, displayed.player, kViewport) !=
        RenderOutcome::Ready)
      break;

    u32 stride_bytes = 0;
    u32* pixels = static_cast<u32*>(framebufferBegin(&fb, &stride_bytes));
    if (!pixels) break;
    const PixelTarget output{pixels, kWidth, kHeight,
                             static_cast<int>(stride_bytes / sizeof(u32))};
    const RasterOutcome drawn = draw_field_pixels(
        output, view, displayed.clock.paused_for_trigger, displayed.area);
    framebufferEnd(&fb);
    if (drawn != RasterOutcome::Ready) break;
  }

  framebufferClose(&fb);
  return 0;
}
