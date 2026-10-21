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
  if (std::strcmp(argv[1], "repair-false-negative") == 0 ||
      std::strcmp(argv[1], "repair-transient-readback") == 0) {
    // Newly launched process: no RAM save survives. Load the valid old
    // journal A while corrupted B remains a genuine on-disk CRC failure.
    WorldState recovered{};
    const FileSaveLoadResult loaded =
        load_field_save_file_detailed(world, path, recovered);
    if (loaded.status != FileSaveStatus::Loaded ||
        !loaded.degraded || loaded.selected_generation != 1 ||
        recovered.player.x != 1 || recovered.pending != Trigger::None)
      return 19;
    runtime.quicksave.world = recovered;
    runtime.quicksave.occupied = true;
    std::vector<std::uint32_t> frame(
        static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
    PixelTarget surface{frame.data(), kRasterWidth, kRasterHeight,
                        kRasterWidth};
    RuntimeControls minus{};
    minus.load_snapshot = true;
    const RuntimeFrame applied = advance_field_runtime(
        world, runtime, tick_step, minus, surface);
    if (applied.status != RuntimeStatus::Rendered ||
        !applied.snapshot_restored)
      return 20;
    // Reproduce a false-negative emulated rename report, but accept the
    // write only once the exact CRC-checked committed bytes are visible.
    const bool first_read_rejected =
        std::strcmp(argv[1], "repair-transient-readback") == 0;
    const JournalInterruption injected =
        first_read_rejected ?
        JournalInterruption::AfterPostPublishFirstReadRejected :
        JournalInterruption::AfterNewSlotRenamedReportedFailure;
    if (store_field_save_file(world, runtime.manual, path, injected)
        != FileSaveStatus::Stored)
      return 21;
    const FileSaveSlot fixed_b =
        read_field_journal_slot(world, path + ".b");
    if (fixed_b.status != FileSaveStatus::Loaded ||
        fixed_b.generation != 2 ||
        fixed_b.world.player.x != 1 ||
        fixed_b.world.pending != Trigger::None)
      return 22;
    std::puts(first_read_rejected ?
        "FRESH_PROCESS_REPAIRED_B_AFTER_TRANSIENT_READBACK" :
        "FRESH_PROCESS_REPAIRED_B_DESPITE_FALSE_RENAME_ERROR");
    return 0;
  }
  if (std::strcmp(argv[1], "expect-healthy-start") == 0) {
    WorldState recovered{};
    const FileSaveLoadResult loaded =
        load_field_save_file_detailed(world, path, recovered);
    if (loaded.status != FileSaveStatus::Loaded ||
        loaded.degraded || loaded.selected_generation != 2 ||
        recovered.player.x != 1 || recovered.pending != Trigger::None)
      return 23;
    std::puts("FRESH_PROCESS_LOADED_REPAIRED_HEALTHY_JOURNAL");
    return 0;
  }
  if (std::strcmp(argv[1], "save-start") == 0) {
    const FileSaveStatus saved =
        store_field_save_file(world, runtime.manual, path);
    if (saved != FileSaveStatus::Stored) return 15;
    std::puts("FIRST_PROCESS_STORED_INITIAL_LOCATION");
    return 0;
  }
  if (std::strcmp(argv[1], "expect-start") == 0) {
    WorldState imported{};
    if (load_field_save_file(world, path, imported) !=
        FileSaveStatus::Loaded) return 16;
    if (imported.player.x != 1 || imported.player.y != 1 ||
        imported.pending != Trigger::None ||
        imported.player.successful_moves != 0)
      return 17;
    runtime.quicksave.world = imported;
    runtime.quicksave.occupied = true;
    std::vector<std::uint32_t> image(
        static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
    PixelTarget target{image.data(), kRasterWidth, kRasterHeight, kRasterWidth};
    RuntimeControls load{};
    load.load_snapshot = true;
    const RuntimeFrame restored = advance_field_runtime(
        world, runtime, tick_step, load, target);
    if (restored.status != RuntimeStatus::Rendered ||
        !restored.snapshot_restored || runtime.manual.player.x != 1 ||
        runtime.manual.pending != Trigger::None)
      return 18;
    std::puts("NEW_PROCESS_FELL_BACK_TO_PREVIOUS_INITIAL_SAVE");
    return 0;
  }
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
