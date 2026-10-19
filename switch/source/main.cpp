#include <switch.h>

#include "field.hpp"
#include "field_world.hpp"
#include "field_view.hpp"
#include "field_pixels.hpp"
#include "field_scenario.hpp"
#include "field_autoplay.hpp"
#include "field_frame_ticks.hpp"
#include "field_runtime.hpp"
#include "field_save_file.hpp"
#include "field_save_feedback.hpp"

#include <algorithm>
#include <cerrno>
#include <sys/stat.h>
#include <cstddef>
#include <cstdint>

namespace {
using namespace wa::field;

constexpr int kWidth = 1280;
constexpr int kHeight = 720;
constexpr int kTileSize = 64;
constexpr Viewport kViewport{11, 7};
constexpr const char* kSaveRoot = "sdmc:/switch/wild_arms_field";
constexpr const char* kSaveBase =
    "sdmc:/switch/wild_arms_field/field-save";

[[nodiscard]] bool ensure_directory(const char* path) noexcept {
  if (::mkdir(path, 0777) == 0) return true;
  if (errno != EEXIST) return false;
  struct stat info{};
  return ::stat(path, &info) == 0 && S_ISDIR(info.st_mode);
}


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

  // Mount SDMC only when not already mounted by the homebrew runtime.
  // Failure is non-fatal: manual gameplay + volatile Y/Minus still work.
  bool mounted_here = false;
  if (fsdevGetDeviceFileSystem("sdmc") == nullptr)
    mounted_here = R_SUCCEEDED(fsdevMountSdmc());
  const bool storage_ready =
      fsdevGetDeviceFileSystem("sdmc") != nullptr &&
      ensure_directory("sdmc:/switch") &&
      ensure_directory(kSaveRoot);

  padConfigureInput(1, HidNpadStyleSet_NpadStandard);
  PadState pad{};
  padInitializeDefault(&pad);

  FieldRuntime runtime = start_field_runtime(
      world, armGetSystemTickFreq(), armGetSystemTick());
  if (!runtime.timer.valid()) {
    framebufferClose(&fb);
    if (mounted_here) (void)fsdevUnmountDevice("sdmc");
    return 4;
  }

  StorageFeedback feedback{};
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
        (pressed & HidNpadButton_B) != 0,
        (pressed & HidNpadButton_Y) != 0,
        (pressed & HidNpadButton_Minus) != 0};
    // In-memory Y/Minus remains the single deterministic gameplay source.
    // On the first Minus after a fresh launch, seed the volatile slot from
    // the newest independently validated SD journal entry. Failed reads
    // NEVER change the live world or a currently occupied RAM quicksave.
    bool imported_from_sd = false;
    bool degraded_sd_journal = false;
    FileSaveStatus attempted_read = FileSaveStatus::Missing;
    const bool fresh_load = input.load_snapshot && !runtime.autoplay &&
        !input.start_demo && !runtime.quicksave.occupied;
    if (fresh_load && storage_ready) {
      WorldState recovered{};
      const FileSaveLoadResult read =
          load_field_save_file_detailed(world, kSaveBase, recovered);
      attempted_read = read.status;
      if (read.status == FileSaveStatus::Loaded) {
        degraded_sd_journal = read.degraded;
        runtime.quicksave.world = recovered;
        runtime.quicksave.occupied = true;
        imported_from_sd = true;
      }
    }
    const RuntimeFrame result = advance_field_runtime(
        world, runtime, armGetSystemTick(), input, output);
    if (result.status != RuntimeStatus::Rendered) {
      framebufferEnd(&fb);
      break;
    }

    // The deterministic game-field framebuffer was drawn first.
    // Storage feedback is an independent short-lived UI overlay, never an
    // input to the canonical host/Switch scenario or snapshot state.
    advance_storage_notice(feedback, result.delta_ms);
    if (result.autoplay) {
      begin_storage_notice(feedback, StorageNotice::None);
    } else if (result.snapshot_stored) {
      const FileSaveStatus written = storage_ready ?
          store_field_save_file(world, runtime.quicksave.world, kSaveBase) :
          FileSaveStatus::Missing;
      begin_storage_notice(feedback,
          storage_save_notice(storage_ready, written));
    } else if (result.snapshot_restored) {
      begin_storage_notice(feedback,
          storage_load_notice(true, imported_from_sd, storage_ready,
                              attempted_read, degraded_sd_journal));
    } else if (result.snapshot_empty) {
      begin_storage_notice(feedback,
          storage_load_notice(false, false, storage_ready,
                              attempted_read));
    }
    (void)draw_storage_notice(output, feedback);
    framebufferEnd(&fb);
  }

  framebufferClose(&fb);
  if (mounted_here) (void)fsdevUnmountDevice("sdmc");
  return 0;
}
