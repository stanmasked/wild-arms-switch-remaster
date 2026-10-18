#include <switch.h>

#include "field.hpp"
#include "field_world.hpp"
#include "field_view.hpp"
#include "field_pixels.hpp"
#include "field_scenario.hpp"
#include "field_autoplay.hpp"
#include "field_frame_ticks.hpp"
#include "field_runtime.hpp"

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

  FieldRuntime runtime = start_field_runtime(
      world, armGetSystemTickFreq(), armGetSystemTick());
  if (!runtime.timer.valid()) {
    framebufferClose(&fb);
    return 4;
  }

  while (appletMainLoop()) {
    padUpdate(&pad);
    const u64 pressed = padGetButtonsDown(&pad);
    if (pressed & HidNpadButton_Plus) break;

    u32 stride_bytes = 0;
    u32* pixels = static_cast<u32*>(framebufferBegin(&fb, &stride_bytes));
    if (!pixels) break;
    const PixelTarget output{pixels, kWidth, kHeight,
                             static_cast<int>(stride_bytes / sizeof(u32))};
    const RuntimeControls input{
        read_pad(pad), (pressed & HidNpadButton_X) != 0,
        (pressed & HidNpadButton_B) != 0};
    const RuntimeFrame result = advance_field_runtime(
        world, runtime, armGetSystemTick(), input, output);
    framebufferEnd(&fb);
    if (result.status != RuntimeStatus::Rendered) break;
  }

  framebufferClose(&fb);
  return 0;
}
