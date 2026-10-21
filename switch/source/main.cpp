#include <switch.h>

#include "field.hpp"
#include "field_world.hpp"
#include "field_view.hpp"
#include "field_pixels.hpp"
#include "field_scenario.hpp"
#include "field_autoplay.hpp"
#include "field_frame_ticks.hpp"
#include "field_runtime.hpp"
#include "field_battle_session.hpp"
#include "field_battle_arm_entry.hpp"
#if defined(WA_ARM_EXPERIMENTAL)
#include "field_battle_arm_training.hpp"
#include "field_arm_reward_file.hpp"
#endif
#include "field_encounters.hpp"
#include "field_save_file.hpp"
#include "field_battle_file.hpp"
#include "field_battle_storage_warning.hpp"
#include "field_save_feedback.hpp"

#include <algorithm>
#include <cerrno>
#include <sys/stat.h>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
using namespace wa::field;

constexpr int kWidth = 1280;
constexpr int kHeight = 720;
constexpr int kTileSize = 64;
constexpr Viewport kViewport{11, 7};
constexpr const char* kSaveRoot = "sdmc:/switch/wild_arms_field";
constexpr const char* kSaveBase =
    "sdmc:/switch/wild_arms_field/field-save";
// Distinct journal namespace; never share a slot with field exploration.
constexpr const char* kBattleSaveBase =
    "sdmc:/switch/wild_arms_field/battle-progress";
#if defined(WA_ARM_EXPERIMENTAL)
constexpr const char* kArmRewardSaveBase =
    "sdmc:/switch/wild_arms_field/arm-rewards";
#endif

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
  // Separate nonpersistent demonstration fight, explicitly opened with R
  // in manual mode; the original exploration runtime stays intact.
  FieldBattleSession battle_scene{};
#if defined(WA_ARM_EXPERIMENTAL)
  // Experimental ARM mode is compiled ONLY with WA_ARM_EXPERIMENTAL=1.
  // Battle state is session-local; rewards use a separate WAER v1 journal, never WABJ.
  ArmTrainingSession arm_scene{};
  arm_scene.reward_storage_warning = !storage_ready;
  if (storage_ready) {
    BattleRewardAccount restored_rewards{};
    const auto loaded_rewards =
        load_arm_reward_file(kArmRewardSaveBase,restored_rewards);
    if (loaded_rewards.status==ArmRewardJournalStatus::Loaded) {
      arm_scene.rewards=restored_rewards;
      arm_scene.reward_storage_warning=loaded_rewards.degraded;
    } else if (loaded_rewards.status!=ArmRewardJournalStatus::Missing) {
      // Never replace two invalid reward slots with a silent zero balance.
      arm_scene.reward_storage_warning=true;
    }
  }
#endif
  bool battle_journal_corrupt = false;
  // Recover only a fully validated independent battle-progress journal.
  // Missing/corrupt records cannot change the default volatile counters.
  if (storage_ready) {
    BattleProgress restored{};
    const auto loaded=load_battle_progress_file(kBattleSaveBase,restored);
    if (loaded.status==BattleJournalStatus::Loaded) {
      battle_scene.history=restored.history;
      battle_scene.rewards=restored.rewards;
    } else {
      // Preserve both bad copies for external recovery. Show the problem
      // only on an explicitly requested ZL panel, never on normal field.
      battle_journal_corrupt=battle_journal_needs_warning(loaded.status);
    }
  }
  // ZR explicitly toggles optional step encounters. Default is off so
  // previous NeXium autoplay, saves and field captures stay unchanged.
  EncounterDirector encounters{};
  while (appletMainLoop()) {
    padUpdate(&pad);
    const u64 pressed = padGetButtonsDown(&pad);
    const u64 held = padGetButtons(&pad);
    if (pressed & HidNpadButton_Plus) break;
    // Pure, unit-tested route: plain R always enters the old battle;
    // opt-in ZL+R is possible only with the explicit build flag.
    const ArmEntryChoice arm_route=select_arm_battle_entry(
#if defined(WA_ARM_EXPERIMENTAL)
        true,
#else
        false,
#endif
        (pressed & HidNpadButton_R) != 0,
        (held & HidNpadButton_ZL) != 0,
        runtime.autoplay,
        battle_scene.active,
#if defined(WA_ARM_EXPERIMENTAL)
        arm_scene.active
#else
        false
#endif
        );
    const bool open_arm=arm_route.open_arm;
    const bool open_battle=arm_route.open_regular;
    // Neither training UI can leak presses into the field save runtime.
    const bool battle_owns_input=arm_route.battle_owns_input;

    u32 stride_bytes = 0;
    u32* pixels = static_cast<u32*>(framebufferBegin(&fb, &stride_bytes));
    if (!pixels) break;
    const PixelTarget output{pixels, kWidth, kHeight,
                             static_cast<int>(stride_bytes / sizeof(u32))};
    const RuntimeControls input = battle_owns_input
        ? RuntimeControls{} : RuntimeControls{
            read_pad(pad), (pressed & HidNpadButton_X) != 0,
            (pressed & HidNpadButton_B) != 0,
            (pressed & HidNpadButton_Y) != 0,
            (pressed & HidNpadButton_Minus) != 0,
            (held & HidNpadButton_L) != 0};
    // In-memory Y/Minus remains the single deterministic gameplay source.
    // On the first Minus after a fresh launch, seed the volatile slot from
    // the newest independently validated SD journal entry. Failed reads
    // NEVER change the live world or a currently occupied RAM quicksave.
    bool imported_from_sd = false;
    bool degraded_sd_journal = false;
    FileSaveStatus attempted_read = FileSaveStatus::Missing;
    const bool fresh_load = input.load_snapshot && !runtime.autoplay &&
        !input.start_demo && !input.view_journal &&
        !runtime.quicksave.occupied;
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

    // Opt-in ZR mode: after four actual successful field steps start
    // the same isolated battle. Never interrupt pending events, journal,
    // snapshot, R training, autoplay or an already active battle.
    const EncounterControls encounter_controls{
        (pressed & HidNpadButton_ZR) != 0,
        !result.autoplay,
        battle_scene.active
#if defined(WA_ARM_EXPERIMENTAL)
            || arm_scene.active
#endif
        ,
        open_battle || open_arm,
        result.snapshot_restored,
        result.journal_visible || input.start_demo || input.cancel_demo ||
            input.save_snapshot || input.load_snapshot ||
            result.inspected != Trigger::None};
    const EncounterFrame encounter_frame =
        advance_field_encounters(encounters, runtime.manual,
                                 encounter_controls);
    if (encounter_frame.status == EncounterStatus::InvalidState) {
      framebufferEnd(&fb);
      break;
    }
    // Enter R for a direct synthetic training fight, or ZR opt-in
    // encounters after sufficient walking. B closes it. While fighting
    // A/Y cannot inspect field events or write exploration snapshots.
    const FieldBattleSessionInput combat_input{
        open_battle || encounter_frame.triggered,
        battle_scene.active && (pressed & HidNpadButton_B) != 0,
        !runtime.autoplay,
        {(held & HidNpadButton_Left) != 0,
         (held & HidNpadButton_Right) != 0,
         (held & HidNpadButton_Up) != 0,
         (held & HidNpadButton_Down) != 0,
         (held & HidNpadButton_A) != 0,
         (held & HidNpadButton_Y) != 0}};
    const BattleSceneFrame battle_frame =
        advance_battle_session(battle_scene, combat_input, output);
    if (battle_frame.status == BattleSceneStatus::InvalidTarget ||
        battle_frame.status == BattleSceneStatus::InvalidBattle ||
        battle_frame.status == BattleSceneStatus::InvalidController) {
      framebufferEnd(&fb);
      break;
    }

#if defined(WA_ARM_EXPERIMENTAL)
    // Dedicated opt-in scene: X=Fire, Minus=Reload, ZR=charged Burst.
    // Ordinary A/Y and D-pad still have their usual in-battle semantics.
    // ARM rewards use only the separate WAER v1 journal; ammo and battle
    // history remain volatile. Never overwrite the ordinary WABJ v1 slots.
    const ArmTrainingInput arm_input{
        open_arm,
        arm_scene.active && (pressed & HidNpadButton_B) != 0,
        !runtime.autoplay,
        {(held & HidNpadButton_Left) != 0,
         (held & HidNpadButton_Right) != 0,
         (held & HidNpadButton_Up) != 0,
         (held & HidNpadButton_Down) != 0,
         (held & HidNpadButton_A) != 0,
         (held & HidNpadButton_Y) != 0},
        {(held & HidNpadButton_X) != 0,
         (held & HidNpadButton_Minus) != 0,
         (held & HidNpadButton_ZR) != 0}};
    const ArmTrainingFrame arm_frame =
        advance_arm_training_session(arm_scene,arm_input,output);
    if (arm_frame.status == ArmTrainingStatus::InvalidTarget ||
        arm_frame.status == ArmTrainingStatus::InvalidState ||
        arm_frame.status == ArmTrainingStatus::InvalidController) {
      framebufferEnd(&fb);
      break;
    }
#endif

#if defined(WA_ARM_EXPERIMENTAL)
    // The ARM prototype owns a distinct WAER journal. It never writes the
    // ordinary WABJ battle-progress or WAFS exploration save slots.
    if (arm_frame.exited &&
        arm_frame.resolution==BattleResolution::Victory) {
      if (storage_ready) {
        const auto saved=store_arm_reward_file(
            arm_scene.rewards,kArmRewardSaveBase);
        arm_scene.reward_storage_warning =
            saved!=ArmRewardJournalStatus::Stored;
        char trace[128]{};
        const int length=std::snprintf(
            trace,sizeof(trace),
            "WA_ARM_REWARDS v1 result=%d exp=%u gella=%u",
            static_cast<int>(saved),
            static_cast<unsigned>(arm_scene.rewards.experience),
            static_cast<unsigned>(arm_scene.rewards.gella));
        if (length>0 && length<static_cast<int>(sizeof(trace)))
          (void)svcOutputDebugString(trace,static_cast<std::size_t>(length));
      } else {
        arm_scene.reward_storage_warning=true;
      }
    }
#endif

    // Only a fully validated first B-close writes battle progress.
    // Never write to field-save.a/.b or the 40-byte exploration record.
    // File errors are nonfatal: gameplay and volatile counters continue.
    if (battle_frame.exited && storage_ready) {
      const BattleProgress record{battle_scene.history,battle_scene.rewards};
      const auto saved=store_battle_progress_file(record,kBattleSaveBase);
      char trace[96]{};
      const int length=std::snprintf(trace,sizeof(trace),
          "WA_BATTLE_PROGRESS v1 result=%d",
          static_cast<int>(saved));
      if (length>0 && length<static_cast<int>(sizeof(trace)))
        (void)svcOutputDebugString(trace,static_cast<std::size_t>(length));
    }

    // The deterministic game-field framebuffer was drawn first.
    // Storage feedback is an independent short-lived UI overlay, never an
    // input to the canonical host/Switch scenario or snapshot state.
    advance_storage_notice(feedback, result.delta_ms);
    if (result.autoplay) {
      begin_storage_notice(feedback, StorageNotice::None);
    } else if (result.snapshot_stored) {
      JournalWriteDiagnostic detail{};
      const FileSaveStatus written = storage_ready ?
          store_field_save_file(world, runtime.quicksave.world, kSaveBase,
                                JournalInterruption::None, &detail) :
          FileSaveStatus::Missing;
      // Structured non-sensitive diagnostic emitted through the Switch debug
      // syscall. NeXium captures it only with NEXIUM_DIAG enabled.
      char trace[320]{};
      const int len = std::snprintf(trace, sizeof(trace),
          "WA_SAVE_TRACE v1 result=%d ready=%d step=%d oldA=%d oldB=%d "
          "tmp=%d pub=%d gen=%llu tries=%u renamed=%d equal=%d errno=%d "
          "count=%u eof=%d more=%d magic=%d crc=%d decoded=%d",
          static_cast<int>(written), storage_ready ? 1 : 0,
          static_cast<int>(detail.step), static_cast<int>(detail.existing_a),
          static_cast<int>(detail.existing_b),
          static_cast<int>(detail.temporary_status),
          static_cast<int>(detail.published_status),
          static_cast<unsigned long long>(detail.intended_generation),
          static_cast<unsigned>(detail.read_attempts),
          detail.rename_succeeded ? 1 : 0,
          detail.published_bytes_equal ? 1 : 0, detail.os_error_code,
          static_cast<unsigned>(detail.postpublish_read.bytes_read),
          detail.postpublish_read.eof_after_probe ? 1 : 0,
          detail.postpublish_read.extra_byte ? 1 : 0,
          detail.postpublish_read.header_ok ? 1 : 0,
          detail.postpublish_read.crc_ok ? 1 : 0,
          detail.postpublish_read.decoded_ok ? 1 : 0);
      if (len > 0 && len < static_cast<int>(sizeof(trace))) {
        (void)svcOutputDebugString(trace, static_cast<std::size_t>(len));
#if defined(WA_NEXIUM_SAVE_TRACE)
        // NeXium's debug syscall may not surface guest strings on the
        // selected nightly. Keep a tiny, non-sensitive second evidence
        // channel in the isolated guest SDMC. This macro is enabled ONLY
        // in the experimental workflow, never the normal Switch build.
        std::FILE* diagnostic = std::fopen(
            "sdmc:/switch/wild_arms_field/save-phase.txt", "wb");
        if (diagnostic != nullptr) {
          (void)std::fwrite(trace, 1, static_cast<std::size_t>(len),
                            diagnostic);
          (void)std::fputc('\n', diagnostic);
          (void)std::fclose(diagnostic);
        }
#endif
      }
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
    // Never draw leftover save feedback over the opaque battle HUD.
    if (!battle_scene.active
#if defined(WA_ARM_EXPERIMENTAL)
        && !arm_scene.active && !open_arm && !arm_frame.exited
#endif
        ) {
      (void)draw_storage_notice(output, feedback);
      // Small opt-in indicator outside the map: golden when ZR mode is
      // active. With encounters off, original pixel captures are identical.
      if (encounters.enabled && !runtime.autoplay)
        fill_raster_rect(output, 1240, 20, 18, 18, rgba(245,183,66));
      // Hold ZL to view session-only victories/defeats/retreats.
      // Never overlay the ordinary map or the canonical B-return frame
      // unless explicitly requested; file save schema remains unchanged.
      if (!runtime.autoplay && (held & HidNpadButton_ZL)) {
        if (draw_field_battle_history(output, battle_scene.history)) {
          draw_battle_reward_balance(output, battle_scene.rewards);
          (void)draw_battle_journal_warning(output, battle_journal_corrupt);
        }
      }
    }
    framebufferEnd(&fb);
  }

  framebufferClose(&fb);
  if (mounted_here) (void)fsdevUnmountDevice("sdmc");
  return 0;
}
