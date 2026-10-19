#include "field_save_file.hpp"
#include "field_runtime.hpp"

#include <cstdio>
#include <cstring>
#include <vector>

using namespace wa::field;

// Separate executable invocation for each phase. The process never shares
// FieldRuntime, FieldSnapshotSlot or static state across a process boundary.
int main(int argc, char** argv) {
  if (argc != 3) return 2;
  const FieldWorld world = make_demo_world();
  if (!world.valid()) return 3;
  const std::string path = argv[2];
  constexpr std::uint64_t frequency = 19200000;
  constexpr std::uint64_t tick_step = 3072000;
  FieldRuntime runtime = start_field_runtime(world, frequency, 0);
  if (!runtime.timer.valid() || runtime.manual.player.x != 1 ||
      runtime.quicksave.occupied) return 4;
  if (std::strcmp(argv[1], "save") == 0) {
    std::vector<std::uint32_t> frame(
        static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
    PixelTarget target{frame.data(), kRasterWidth, kRasterHeight,
                       kRasterWidth};
    for (int i = 1; i <= 3; ++i) {
      const RuntimeControls right{PadSample{.dpad_right = true}};
      if (advance_field_runtime(world, runtime, tick_step * i, right,
                                target).status != RuntimeStatus::Rendered)
        return 5;
    }
    if (runtime.manual.player.x != 4 ||
        runtime.manual.pending != Trigger::Event ||
        !runtime.manual.clock.paused_for_trigger) return 6;
    if (store_field_save_file(world, runtime.manual, path) !=
        FileSaveStatus::Stored) return 7;
    std::puts("FIRST_PROCESS_WRITTEN_PENDING_EVENT");
    return 0;
  }
  if (std::strcmp(argv[1], "load") == 0) {
    // New process starts at (1,1) with an empty snapshot.
    WorldState imported{};
    if (load_field_save_file(world, path, imported) !=
        FileSaveStatus::Loaded) return 8;
    if (imported.player.x != 4 || imported.player.y != 1 ||
        imported.pending != Trigger::Event ||
        !imported.clock.paused_for_trigger) return 9;
    runtime.quicksave.world = imported;
    runtime.quicksave.occupied = true;
    std::vector<std::uint32_t> frame(
        static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
    PixelTarget target{frame.data(), kRasterWidth, kRasterHeight,
                       kRasterWidth};
    RuntimeControls restore{};
    restore.load_snapshot = true;
    const RuntimeFrame restored = advance_field_runtime(
        world, runtime, tick_step, restore, target);
    if (restored.status != RuntimeStatus::Rendered ||
        !restored.snapshot_restored ||
        runtime.manual.player.x != 4 ||
        runtime.manual.pending != Trigger::Event) return 10;
    const RuntimeControls confirm{PadSample{.confirm = true}};
    const RuntimeFrame acknowledged = advance_field_runtime(
        world, runtime, tick_step*2, confirm, target);
    if (acknowledged.status != RuntimeStatus::Rendered ||
        runtime.manual.pending != Trigger::None) return 11;
    std::puts("SECOND_PROCESS_LOADED_AND_ACKNOWLEDGED_EVENT");
    return 0;
  }
  if (std::strcmp(argv[1], "expect-bad") == 0) {
    const WorldState before = runtime.manual;
    const FileSaveStatus status =
        load_field_save_file(world, path, runtime.manual);
    if (status != FileSaveStatus::Corrupt &&
        status != FileSaveStatus::Missing) return 12;
    if (runtime.manual.player.x != before.player.x ||
        runtime.manual.player.y != before.player.y ||
        runtime.manual.pending != before.pending) return 13;
    std::puts("FRESH_PROCESS_REJECTED_BROKEN_FILE_UNCHANGED");
    return 0;
  }
  return 14;
}
