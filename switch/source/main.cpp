#include <switch.h>

#include "field.hpp"
#include "field_controls.hpp"
#include "field_view.hpp"

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

void fill_rect(u32* pixels, const u32 pitch, int x, int y, int w, int h,
               const u32 color) noexcept {
  const int x0 = std::clamp(x, 0, kWidth);
  const int y0 = std::clamp(y, 0, kHeight);
  const int x1 = std::clamp(x + w, 0, kWidth);
  const int y1 = std::clamp(y + h, 0, kHeight);
  for (int row = y0; row < y1; ++row) {
    u32* dest = pixels + static_cast<std::size_t>(row) * pitch;
    for (int col = x0; col < x1; ++col)
      dest[col] = color;
  }
}

u32 terrain_color(const CellKind kind) noexcept {
  switch (kind) {
    case CellKind::Wall: return RGBA8_MAXALPHA(47, 68, 87);
    case CellKind::Floor: return RGBA8_MAXALPHA(174, 155, 115);
    case CellKind::Event: return RGBA8_MAXALPHA(245, 183, 66);
    case CellKind::Exit: return RGBA8_MAXALPHA(63, 191, 138);
    case CellKind::Outside: return RGBA8_MAXALPHA(14, 20, 34);
  }
  return RGBA8_MAXALPHA(14, 20, 34);
}

void paint(u32* pixels, const u32 stride_bytes, const RenderFrame& frame,
           const bool paused) noexcept {
  const u32 pitch = stride_bytes / sizeof(u32);
  fill_rect(pixels, pitch, 0, 0, kWidth, kHeight,
            RGBA8_MAXALPHA(14, 20, 34));

  const int start_x = (kWidth - frame.width * kTileSize) / 2;
  const int start_y = (kHeight - frame.height * kTileSize) / 2;
  for (int y = 0; y < frame.height; ++y) {
    for (int x = 0; x < frame.width; ++x) {
      const RenderCell* cell = frame.at(x, y);
      if (!cell) continue;
      const int left = start_x + x * kTileSize;
      const int top = start_y + y * kTileSize;
      fill_rect(pixels, pitch, left + 1, top + 1,
                kTileSize - 2, kTileSize - 2,
                terrain_color(cell->terrain));
      if (cell->player) {
        const int cx = left + kTileSize / 2;
        const int cy = top + kTileSize / 2;
        fill_rect(pixels, pitch, cx - 19, cy - 19, 38, 38,
                  paused ? RGBA8_MAXALPHA(246, 246, 246)
                         : RGBA8_MAXALPHA(201, 67, 76));
        const int marker_size = 10;
        int mx = cx - marker_size / 2;
        int my = cy - marker_size / 2;
        switch (frame.player_facing) {
          case Direction::Up: my -= 15; break;
          case Direction::Down: my += 15; break;
          case Direction::Left: mx -= 15; break;
          case Direction::Right: mx += 15; break;
          case Direction::None: break;
        }
        fill_rect(pixels, pitch, mx, my, marker_size, marker_size,
                  RGBA8_MAXALPHA(22, 27, 42));
      }
    }
  }
  // Status bar: amber when waiting for A to acknowledge an event/exit.
  fill_rect(pixels, pitch, 0, 0, kWidth, 10,
            paused ? RGBA8_MAXALPHA(246, 183, 66)
                   : RGBA8_MAXALPHA(63, 191, 138));
}

}  // namespace

int main() {
  const Map map{
    11, 7,
    "###########"
    "#...!.....#"
    "#.#.###.#.#"
    "#...#...#.#"
    "#.#...#...#"
    "#.....E...#"
    "###########"};
  if (!map.valid()) return 1;

  Framebuffer fb{};
  Result setup = framebufferCreate(&fb, nwindowGetDefault(), kWidth, kHeight,
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

  State player{1, 1};
  MovementClock clock{};
  PadDecoder decoder{};
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

    const PadFrameResult result =
        advance_pad_frame(decoder, clock, player, map, read_pad(pad), delta);
    (void)result;
    if (build_view(view, map, player, kViewport) != RenderOutcome::Ready)
      break;

    u32 stride_bytes = 0;
    u32* pixels = static_cast<u32*>(framebufferBegin(&fb, &stride_bytes));
    if (!pixels) break;
    paint(pixels, stride_bytes, view, clock.paused_for_trigger);
    framebufferEnd(&fb);
  }

  framebufferClose(&fb);
  return 0;
}
