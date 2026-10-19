#include "field_runtime.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <initializer_list>
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

void test_manual_adjacent_inspection_renders_timed_outline() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface surface;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  const RuntimeControls right{PadSample{.dpad_right=true}};
  require(advance_field_runtime(world, rt, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);
  for (int i=1; i<=2; ++i)
    require(advance_field_runtime(world, rt, step*i, right,
                                  surface.target).status ==
            RuntimeStatus::Rendered);
  require(rt.manual.player.x == 3 &&
          rt.manual.player.facing == Direction::Right &&
          rt.manual.pending == Trigger::None);
  const RuntimeControls inspect{PadSample{.confirm=true}};
  const auto looked = advance_field_runtime(
      world, rt, step*3, inspect, surface.target);
  require(looked.status == RuntimeStatus::Rendered &&
          looked.inspected == Trigger::Event &&
          rt.inspection.kind == Trigger::Event &&
          rt.inspection.remaining_ms == kFieldInspectionDurationMs);
  require(rt.manual.player.x == 3 &&
          rt.manual.player.successful_moves == 2 &&
          rt.manual.pending == Trigger::None);
  // Full-sized demo map has origin (288,136), marker (4,1).
  // Outline is drawn at left+7,top+7, unlike the original terrain fill.
  constexpr int px = 288 + 4*64 + 7;
  constexpr int py = 136 + 64 + 7;
  require(surface.pixel(px,py) == rgba(255,247,172));
  const auto held = advance_field_runtime(
      world, rt, step*4, inspect, surface.target);
  require(held.status == RuntimeStatus::Rendered &&
          held.inspected == Trigger::None &&
          surface.pixel(px,py) == rgba(255,247,172));
  const auto elapsed = advance_field_runtime(
      world, rt, step*10, {}, surface.target);
  require(elapsed.status == RuntimeStatus::Rendered &&
          rt.inspection.kind == Trigger::None &&
          surface.pixel(px,py) == terrain_rgba(CellKind::Event));
  surface.assert_guards();
}

void test_manual_inspection_caption_and_stale_target_invalidation() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world,kSwitchTicksPerSecond,0);
  Surface display;
  constexpr std::uint64_t step = kSwitchTicksPerSecond*160/1000;
  const RuntimeControls right{PadSample{.dpad_right=true}};
  require(advance_field_runtime(world,rt,0,{},display.target).status==
          RuntimeStatus::Rendered);
  (void)advance_field_runtime(world,rt,step,right,display.target);
  (void)advance_field_runtime(world,rt,step*2,right,display.target);
  require(rt.manual.player.x==3);
  const RuntimeControls inspect{PadSample{.confirm=true}};
  auto result=advance_field_runtime(world,rt,step*3,inspect,display.target);
  require(result.inspected==Trigger::Event);
  require(rt.inspection.kind==Trigger::Event);
  require(display.pixel(kInspectionPanelX,kInspectionPanelY)==
          rgba(255,247,172));
  require(display.pixel(kInspectionPanelX+3,kInspectionPanelY+3)==
          rgba(17,26,40));
  // First glyph "E": top row is five white pixels after raster scale.
  require(display.pixel(kInspectionPanelX+20,
                        kInspectionPanelY+20)==rgba(246,247,252));
  // Separate overlay is not serialized into the canonical world state.
  require(rt.manual.player.x==3 && rt.manual.player.successful_moves==2);
  // Move away from the inspected target before the 900-ms timer expires.
  const RuntimeControls left{PadSample{.dpad_left=true}};
  (void)advance_field_runtime(world,rt,step*4,left,display.target);
  require(rt.manual.player.x==2 &&
          rt.inspection.kind==Trigger::None);
  require(display.pixel(kInspectionPanelX,kInspectionPanelY)==
          rgba(14,20,34));
  display.assert_guards();
}

void test_caption_kind_guard_and_exit_glyphs() {
  Surface display;
  const auto untouched=display.buffer;
  require(!draw_inspection_caption(display.target,Trigger::None));
  require(display.buffer==untouched);
  require(inspection_caption(Trigger::Event)[0]=='E');
  require(inspection_caption(Trigger::Exit)[1]=='X');
  require(draw_inspection_caption(display.target,Trigger::Exit));
  require(display.pixel(kInspectionPanelX,kInspectionPanelY)==
          rgba(172,255,230));
  require(display.pixel(kInspectionPanelX+20+15,
                        kInspectionPanelY+20)==rgba(246,247,252));
  display.assert_guards();
  const PixelTarget invalid{nullptr,kRasterWidth,kRasterHeight,kRasterWidth};
  require(!draw_inspection_caption(invalid,Trigger::Exit));
}


void test_manual_event_clue_recording_is_explicit_and_unique() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world,kSwitchTicksPerSecond,0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond*160/1000;
  const RuntimeControls right{PadSample{.dpad_right=true}};
  const RuntimeControls inspect{PadSample{.confirm=true}};
  const RuntimeControls log_clue{{},false,true};
  require(advance_field_runtime(world,rt,0,{},screen.target).status ==
          RuntimeStatus::Rendered);
  (void)advance_field_runtime(world,rt,step,right,screen.target);
  (void)advance_field_runtime(world,rt,step*2,right,screen.target);
  require(rt.manual.player.x==3 && rt.discoveries.count==0);
  auto looked=advance_field_runtime(world,rt,step*3,inspect,screen.target);
  require(looked.inspected==Trigger::Event && !looked.clue_recorded);
  require(rt.discoveries.count==0 && rt.inspection.logged==false);
  const auto written=advance_field_runtime(
      world,rt,step*4,log_clue,screen.target);
  require(written.status==RuntimeStatus::Rendered &&
          written.clue_recorded && !written.clue_already_recorded &&
          written.clue_count==1 && rt.discoveries.count==1 &&
          rt.inspection.logged);
  require(rt.manual.player.x==3 && rt.manual.player.successful_moves==2 &&
          rt.manual.pending==Trigger::None);
  require(inspection_caption(Trigger::Event,rt.inspection.logged)[0]=='C');
  require(screen.pixel(kInspectionPanelX,kInspectionPanelY)==
          rgba(105,160,230));
  screen.assert_guards();

  // B again while holding the same inspection never awards progress twice.
  const auto duplicate=advance_field_runtime(
      world,rt,step*5,log_clue,screen.target);
  require(!duplicate.clue_recorded && duplicate.clue_already_recorded &&
          duplicate.clue_count==1 && rt.discoveries.count==1);
  // After the caption expires, A then B can revisit without incrementing.
  // 960 ms is inside the allowed 1000-ms tick window. A larger
  // single gap would intentionally be treated as a suspended applet.
  (void)advance_field_runtime(world,rt,step*11,{},screen.target);
  require(rt.inspection.kind==Trigger::None);
  (void)advance_field_runtime(world,rt,step*12,inspect,screen.target);
  const auto revisit=advance_field_runtime(
      world,rt,step*13,log_clue,screen.target);
  require(revisit.clue_already_recorded && !revisit.clue_recorded &&
          rt.discoveries.count==1);
  // Ordinary manual snapshot preserves only the world, not the clue
  // ledger; in-session log remains while saving/loading.
  const RuntimeControls save{{},false,false,true,false};
  const auto saved=advance_field_runtime(
      world,rt,step*14,save,screen.target);
  require(saved.snapshot_stored && rt.discoveries.count==1);
  const RuntimeControls load{{},false,false,false,true};
  const auto reloaded=advance_field_runtime(
      world,rt,step*15,load,screen.target);
  require(reloaded.snapshot_restored && rt.discoveries.count==1 &&
          rt.inspection.kind==Trigger::None);
}

void test_modal_save_load_and_demo_cannot_replay_held_A() {
  const FieldWorld world = make_demo_world();
  Surface surface;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  const RuntimeControls a{PadSample{.confirm = true}};
  const RuntimeControls save_a{
      PadSample{.confirm = true}, false, false, true};
  const RuntimeControls load_a{
      PadSample{.confirm = true}, false, false, false, true};
  const RuntimeControls save{{}, false, false, true};
  const RuntimeControls start{{}, true};
  const RuntimeControls cancel_a{
      PadSample{.confirm = true}, false, true};

  // Save while A is held: saving takes precedence, and A must not
  // become a phantom new inspection when Y is released.
  FieldRuntime saved = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  saved.manual.player.x = 3;
  saved.manual.player.facing = Direction::Right;
  require(advance_field_runtime(world, saved, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeFrame storing = advance_field_runtime(
      world, saved, step, save_a, surface.target);
  require(storing.snapshot_stored && storing.inspected == Trigger::None &&
          saved.manual.decoder.confirm_down &&
          saved.inspection.kind == Trigger::None);
  const RuntimeFrame held_after_save = advance_field_runtime(
      world, saved, step * 2, a, surface.target);
  require(held_after_save.status == RuntimeStatus::Rendered &&
          held_after_save.inspected == Trigger::None &&
          saved.inspection.kind == Trigger::None);
  (void)advance_field_runtime(world, saved, step * 3, {}, surface.target);
  require(advance_field_runtime(world, saved, step * 4, a, surface.target).
          inspected == Trigger::Event);

  // A pending event was saved with A released. Reloading under held A
  // must NOT acknowledge it using the historical decoder state.
  FieldRuntime loaded = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  loaded.manual.player.x = 4;
  loaded.manual.player.y = 1;
  loaded.manual.pending = Trigger::Event;
  loaded.manual.clock.paused_for_trigger = true;
  require(advance_field_runtime(world, loaded, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);
  require(advance_field_runtime(world, loaded, step, save, surface.target).
          snapshot_stored);
  require(advance_field_runtime(world, loaded, step * 2, a, surface.target).
          status == RuntimeStatus::Rendered &&
          loaded.manual.pending == Trigger::None);
  const RuntimeFrame restored = advance_field_runtime(
      world, loaded, step * 3, load_a, surface.target);
  require(restored.snapshot_restored &&
          loaded.manual.pending == Trigger::Event &&
          loaded.manual.decoder.confirm_down);
  const RuntimeFrame held_after_load = advance_field_runtime(
      world, loaded, step * 4, a, surface.target);
  require(held_after_load.status == RuntimeStatus::Rendered &&
          loaded.manual.pending == Trigger::Event &&
          loaded.manual.clock.paused_for_trigger);
  (void)advance_field_runtime(world, loaded, step * 5, {}, surface.target);
  require(advance_field_runtime(world, loaded, step * 6, a, surface.target).
          status == RuntimeStatus::Rendered &&
          loaded.manual.pending == Trigger::None);

  // B exits the demo while A is held. Manual mode must not replay
  // that physical A as an inspection when its first frame is sampled.
  FieldRuntime demo = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  require(advance_field_runtime(world, demo, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);
  require(advance_field_runtime(world, demo, step, start, surface.target).
          status == RuntimeStatus::Rendered && demo.autoplay);
  require(advance_field_runtime(world, demo, step * 2, cancel_a,
                                surface.target).status ==
          RuntimeStatus::Rendered && !demo.autoplay &&
          demo.manual.decoder.confirm_down);
  demo.manual.player.x = 3;
  demo.manual.player.facing = Direction::Right;
  require(advance_field_runtime(world, demo, step * 3, a, surface.target).
          inspected == Trigger::None);
  (void)advance_field_runtime(world, demo, step * 4, {}, surface.target);
  require(advance_field_runtime(world, demo, step * 5, a, surface.target).
          inspected == Trigger::Event);
  surface.assert_guards();
}

void test_simultaneous_A_and_B_cannot_collect_before_inspection() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  require(advance_field_runtime(world, rt, 0, {}, screen.target).status ==
          RuntimeStatus::Rendered);
  rt.manual.player.x = 3;
  rt.manual.player.y = 1;
  rt.manual.player.facing = Direction::Right;

  // Two edges sampled together must produce only the inspection.
  const RuntimeControls a_and_b{PadSample{.confirm = true}, false, true};
  const RuntimeFrame simultaneous = advance_field_runtime(
      world, rt, step, a_and_b, screen.target);
  require(simultaneous.status == RuntimeStatus::Rendered &&
          simultaneous.inspected == Trigger::Event &&
          !simultaneous.clue_recorded &&
          !simultaneous.clue_already_recorded &&
          simultaneous.clue_count == 0 &&
          rt.discoveries.count == 0 &&
          !rt.inspection.logged &&
          rt.inspection.kind == Trigger::Event &&
          rt.manual.player.x == 3);

  // A second, independently sampled B press collects the displayed clue.
  require(advance_field_runtime(world, rt, step * 2, {},
                                screen.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeControls b{{}, false, true};
  const RuntimeFrame recorded = advance_field_runtime(
      world, rt, step * 3, b, screen.target);
  require(recorded.status == RuntimeStatus::Rendered &&
          recorded.inspected == Trigger::None &&
          recorded.clue_recorded && recorded.clue_count == 1 &&
          rt.inspection.logged && rt.discoveries.count == 1 &&
          rt.discoveries.entries[0].area == 0 &&
          rt.discoveries.entries[0].x == 4 &&
          rt.discoveries.entries[0].y == 1);
  screen.assert_guards();
}

void test_b_does_not_record_without_inspected_event() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt=start_field_runtime(world,kSwitchTicksPerSecond,0);
  Surface screen;
  const RuntimeControls b{{},false,true};
  const auto noop=advance_field_runtime(
      world,rt,0,b,screen.target);
  require(noop.status==RuntimeStatus::Rendered &&
          !noop.clue_recorded && rt.discoveries.count==0);
  screen.assert_guards();
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

void test_autoplay_exit_rejects_corrupt_discoveries_transactionally() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  const RuntimeControls start{{}, true};
  const RuntimeControls cancel{{}, false, true};

  require(advance_field_runtime(world, rt, 0, {}, screen.target).status ==
          RuntimeStatus::Rendered);
  require(record_discovery(world, rt.discoveries, 0, 4, 1) ==
          DiscoveryResult::Recorded);
  require(advance_field_runtime(world, rt, step, start, screen.target).
          status == RuntimeStatus::Rendered && rt.autoplay);
  // An invalid second entry can be introduced while autoplay is active,
  // which intentionally ignores the dormant manual journal.
  rt.discoveries.count = 2;
  rt.discoveries.entries[1] = {1, 0, 0};
  const auto before_pixels = screen.buffer;
  const auto before_tick = rt.timer.previous_tick;
  const int before_x = rt.manual.player.x;
  const RuntimeFrame rejected = advance_field_runtime(
      world, rt, step * 2, cancel, screen.target);
  require(rejected.status == RuntimeStatus::InvalidSimulation &&
          rt.autoplay && rt.manual.player.x == before_x &&
          rt.timer.previous_tick == before_tick &&
          screen.buffer == before_pixels &&
          rt.discoveries.count == 2);
  // Recover the journal in place; a valid first clue survives exiting
  // autoplay, because cancellation is not a new game process.
  rt.discoveries.entries[1] = {1, 4, 3};
  const RuntimeFrame accepted = advance_field_runtime(
      world, rt, step * 2, cancel, screen.target);
  require(accepted.status == RuntimeStatus::Rendered &&
          !rt.autoplay && rt.manual.area == 0 &&
          rt.manual.player.x == 1 &&
          rt.discoveries.count == 2);
  require(valid_discovery_journal(world, rt.discoveries));
  screen.assert_guards();
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
void test_held_journal_freezes_inputs_and_shows_session_clues() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world,kSwitchTicksPerSecond,0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond*160/1000;
  const RuntimeControls right{PadSample{.dpad_right=true}};
  RuntimeControls journal_right = right;
  journal_right.view_journal = true;
  auto initial = advance_field_runtime(world,rt,0,{},screen.target);
  require(initial.status==RuntimeStatus::Rendered && !initial.journal_visible);
  auto held=advance_field_runtime(world,rt,step,journal_right,screen.target);
  require(held.journal_visible && held.clue_count==0 &&
          rt.manual.player.x==1 && !held.snapshot_stored);
  require(screen.pixel(kJournalPanelX,kJournalPanelY)==rgba(105,160,230));
  // X+L on the same frame must not bypass the modal journal.
  const RuntimeControls journal_start{{},true,false,false,false,true};
  const auto blocked_demo=advance_field_runtime(
      world,rt,step,journal_start,screen.target);
  require(blocked_demo.journal_visible && !rt.autoplay &&
          rt.manual.player.x==1);
  (void)advance_field_runtime(world,rt,step*2,right,screen.target);
  (void)advance_field_runtime(world,rt,step*3,right,screen.target);
  require(rt.manual.player.x==3 && rt.manual.pending==Trigger::None);
  const RuntimeControls inspect{PadSample{.confirm=true}};
  require(advance_field_runtime(world,rt,step*4,inspect,screen.target).
          inspected==Trigger::Event);
  RuntimeControls journal_record{{},false,true};
  journal_record.view_journal=true;
  const auto blocked=advance_field_runtime(
      world,rt,step*5,journal_record,screen.target);
  require(blocked.journal_visible && !blocked.clue_recorded &&
          rt.discoveries.count==0 && rt.manual.player.x==3);
  const RuntimeControls record{{},false,true};
  const auto collected=advance_field_runtime(
      world,rt,step*6,record,screen.target);
  require(collected.clue_recorded && collected.clue_count==1);
  RuntimeControls journal_save{{},false,false,true,false,true};
  const auto view=advance_field_runtime(
      world,rt,step*7,journal_save,screen.target);
  require(view.journal_visible && view.clue_count==1 &&
          !view.snapshot_stored && !rt.quicksave.occupied);
  require(screen.pixel(kJournalPanelX,kJournalPanelY)==rgba(105,160,230));
  screen.assert_guards();

  // A tampered journal fails before any buffer write or state change.
  rt.discoveries.count=kDiscoveryCapacity+1;
  const auto before_pixels=screen.buffer;
  const auto before_tick=rt.timer.previous_tick;
  const auto invalid=advance_field_runtime(
      world,rt,step*8,journal_right,screen.target);
  require(invalid.status==RuntimeStatus::InvalidSimulation &&
          screen.buffer==before_pixels &&
          rt.timer.previous_tick==before_tick);
}



void test_l_held_journal_freezes_inspection_timeout() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface image;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  require(advance_field_runtime(world, rt, 0, {}, image.target).status ==
          RuntimeStatus::Rendered);
  rt.manual.player.x = 3;
  rt.manual.player.y = 1;
  rt.manual.player.facing = Direction::Right;
  const RuntimeControls inspect{PadSample{.confirm = true}};
  const RuntimeFrame looked = advance_field_runtime(
      world, rt, step, inspect, image.target);
  require(looked.inspected == Trigger::Event &&
          rt.inspection.remaining_ms == kFieldInspectionDurationMs);
  const RuntimeControls held{{}, false, false, false, false, true};
  for (int i = 2; i <= 9; ++i) {
    const RuntimeFrame frame = advance_field_runtime(
        world, rt, step * static_cast<std::uint64_t>(i), held, image.target);
    require(frame.status == RuntimeStatus::Rendered &&
            frame.journal_visible && frame.inspected == Trigger::None);
    require(rt.inspection.kind == Trigger::Event &&
            rt.inspection.remaining_ms == kFieldInspectionDurationMs);
  }
  // More than 900ms has elapsed in wall-clock time, but the inspection
  // still has time left because L was held throughout.
  const RuntimeFrame released = advance_field_runtime(
      world, rt, step * 10, {}, image.target);
  require(released.status == RuntimeStatus::Rendered &&
          !released.journal_visible &&
          rt.inspection.kind == Trigger::Event &&
          rt.inspection.remaining_ms ==
              kFieldInspectionDurationMs - 160);
  constexpr int inspected_pixel_x = 288 + 4 * 64 + 7;
  constexpr int inspected_pixel_y = 136 + 64 + 7;
  require(image.pixel(inspected_pixel_x, inspected_pixel_y) ==
          rgba(255, 247, 172));
  // B still records the exact inspected clue even after holding the
  // journal longer than the normal 900-ms inspection lifetime.
  const RuntimeControls record{{}, false, true};
  const RuntimeFrame written = advance_field_runtime(
      world, rt, step * 11, record, image.target);
  require(written.status == RuntimeStatus::Rendered &&
          written.clue_recorded && written.clue_count == 1 &&
          rt.discoveries.entries[0].area == 0 &&
          rt.discoveries.entries[0].x == 4 &&
          rt.discoveries.entries[0].y == 1);
  const RuntimeFrame expired = advance_field_runtime(
      world, rt, step * 17, {}, image.target);
  require(expired.status == RuntimeStatus::Rendered &&
          rt.inspection.kind == Trigger::None);
  image.assert_guards();
}


void test_l_modal_does_not_replay_held_A_on_release() {
  const FieldWorld world = make_demo_world();
  Surface surface;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  const RuntimeControls held_a{
      PadSample{.confirm = true}, false, false, false, false, true};
  const RuntimeControls just_a{PadSample{.confirm = true}};

  // A pressed under the journal must not inspect an adjacent ! when
  // L is released while A remains down. A genuine re-press does inspect.
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  rt.manual.player.x = 3;
  rt.manual.player.y = 1;
  rt.manual.player.facing = Direction::Right;
  require(advance_field_runtime(world, rt, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeFrame held = advance_field_runtime(
      world, rt, step, held_a, surface.target);
  require(held.status == RuntimeStatus::Rendered &&
          held.journal_visible && held.inspected == Trigger::None &&
          rt.manual.decoder.confirm_down);
  const RuntimeFrame still_a = advance_field_runtime(
      world, rt, step * 2, just_a, surface.target);
  require(still_a.status == RuntimeStatus::Rendered &&
          !still_a.journal_visible && still_a.inspected == Trigger::None &&
          rt.inspection.kind == Trigger::None);
  require(advance_field_runtime(world, rt, step * 3, {},
                                surface.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeFrame repressed = advance_field_runtime(
      world, rt, step * 4, just_a, surface.target);
  require(repressed.status == RuntimeStatus::Rendered &&
          repressed.inspected == Trigger::Event &&
          rt.manual.player.x == 3 && rt.manual.pending == Trigger::None);

  // The same edge-suppression policy protects pending event acknowledgement.
  FieldRuntime pending = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  pending.manual.player.x = 4;
  pending.manual.player.y = 1;
  pending.manual.pending = Trigger::Event;
  pending.manual.clock.carry_ms = 0;
  pending.manual.clock.held = Direction::None;
  pending.manual.clock.paused_for_trigger = true;
  require(advance_field_runtime(world, pending, 0, {},
                                surface.target).status ==
          RuntimeStatus::Rendered);
  require(advance_field_runtime(world, pending, step, held_a,
                                surface.target).journal_visible);
  const RuntimeFrame no_ack = advance_field_runtime(
      world, pending, step * 2, just_a, surface.target);
  require(no_ack.status == RuntimeStatus::Rendered &&
          pending.manual.pending == Trigger::Event &&
          pending.manual.clock.paused_for_trigger);
  require(advance_field_runtime(world, pending, step * 3, {},
                                surface.target).status ==
          RuntimeStatus::Rendered);
  const RuntimeFrame acknowledged = advance_field_runtime(
      world, pending, step * 4, just_a, surface.target);
  require(acknowledged.status == RuntimeStatus::Rendered &&
          pending.manual.pending == Trigger::None &&
          !pending.manual.clock.paused_for_trigger);
  surface.assert_guards();
}

void test_journal_releases_old_partial_movement_cadence() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface surface;
  constexpr std::uint64_t half_cadence_ticks =
      kSwitchTicksPerSecond * 80 / 1000;
  const RuntimeControls right{PadSample{.dpad_right = true}};
  const RuntimeControls held_journal{
      PadSample{.dpad_right = true}, false, false, false, false, true};
  require(advance_field_runtime(world, rt, 0, {}, surface.target).status ==
          RuntimeStatus::Rendered);

  // An 80ms D-pad hold pays only half the required 160ms cadence.
  const RuntimeFrame waiting = advance_field_runtime(
      world, rt, half_cadence_ticks, right, surface.target);
  require(waiting.status == RuntimeStatus::Rendered &&
          rt.manual.player.x == 1 &&
          rt.manual.clock.carry_ms == 80 &&
          rt.manual.clock.held == Direction::Right);

  // L opens the journal and intentionally drops that stale 80ms debt.
  for (std::uint64_t frame = 2; frame <= 8; ++frame) {
    const RuntimeFrame modal = advance_field_runtime(
        world, rt, half_cadence_ticks * frame, held_journal,
        surface.target);
    require(modal.status == RuntimeStatus::Rendered &&
            modal.journal_visible &&
            rt.manual.player.x == 1 &&
            rt.manual.clock.carry_ms == 0 &&
            rt.manual.clock.held == Direction::None);
  }

  // 80ms after L release is not enough to move: the old half-period
  // must not be replayed. A second 80ms is required for one step.
  const RuntimeFrame resumed = advance_field_runtime(
      world, rt, half_cadence_ticks * 9, right, surface.target);
  require(resumed.status == RuntimeStatus::Rendered &&
          !resumed.journal_visible &&
          rt.manual.player.x == 1 &&
          rt.manual.clock.carry_ms == 80 &&
          rt.manual.clock.held == Direction::Right);
  const RuntimeFrame moved = advance_field_runtime(
      world, rt, half_cadence_ticks * 10, right, surface.target);
  require(moved.status == RuntimeStatus::Rendered &&
          rt.manual.player.x == 2 &&
          rt.manual.player.successful_moves == 1 &&
          rt.manual.clock.carry_ms == 0);
  surface.assert_guards();
}

void test_manual_preflight_rejects_corrupt_ledger_without_L() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  require(advance_field_runtime(world, rt, 0, {}, screen.target).status ==
          RuntimeStatus::Rendered);

  const auto original_pixels = screen.buffer;
  const auto original_tick = rt.timer.previous_tick;
  const auto original_x = rt.manual.player.x;

  // First entry is valid, but a later out-of-map clue is corrupt.
  // Ordinary movement, B and L must reject the entire malformed ledger.
  rt.discoveries.count = 2;
  rt.discoveries.entries[0] = {0, 4, 1};
  rt.discoveries.entries[1] = {1, -3, 3};
  const RuntimeControls right{PadSample{.dpad_right = true}};
  const RuntimeControls collect{{}, false, true};
  const RuntimeControls journal{{}, false, false, false, false, true};
  const RuntimeControls demo{{}, true};
  const RuntimeControls save{{}, false, false, true};
  const RuntimeControls load{{}, false, false, false, true};
  for (const RuntimeControls& attempt :
       {right, collect, journal, demo, save, load}) {
    const RuntimeFrame result =
        advance_field_runtime(world, rt, step, attempt, screen.target);
    require(result.status == RuntimeStatus::InvalidSimulation &&
            screen.buffer == original_pixels &&
            rt.timer.previous_tick == original_tick &&
            rt.manual.player.x == original_x &&
            rt.discoveries.count == 2 && !rt.quicksave.occupied &&
            !rt.autoplay);
  }

  // Repair the second entry and confirm input works normally again.
  rt.discoveries.entries[1] = {1, 4, 3};
  const RuntimeFrame repaired =
      advance_field_runtime(world, rt, step, right, screen.target);
  require(repaired.status == RuntimeStatus::Rendered &&
          rt.manual.player.x == 2 && rt.discoveries.count == 2);

  // Even a structurally valid journal must not mask a corrupt world
  // pending-event state while displaying its panel.
  const auto valid_pixels = screen.buffer;
  const auto valid_tick = rt.timer.previous_tick;
  rt.manual.pending = Trigger::Event;
  rt.manual.clock.paused_for_trigger = true;
  rt.manual.clock.carry_ms = 0;
  rt.manual.clock.held = Direction::None;
  const RuntimeFrame corrupt_world =
      advance_field_runtime(world, rt, step * 2, journal, screen.target);
  require(corrupt_world.status == RuntimeStatus::InvalidSimulation &&
          screen.buffer == valid_pixels &&
          rt.timer.previous_tick == valid_tick &&
          rt.manual.player.x == 2 &&
          rt.discoveries.count == 2);
  screen.assert_guards();
}

void test_cross_area_discovery_journal_survives_world_and_snapshot_changes() {
  const FieldWorld world = make_demo_world();
  FieldRuntime rt = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  Surface screen;
  constexpr std::uint64_t step = kSwitchTicksPerSecond * 160 / 1000;
  std::uint64_t tick = 0;
  const RuntimeControls right{PadSample{.dpad_right = true}};
  const RuntimeControls down{PadSample{.dpad_down = true}};
  const RuntimeControls inspect{PadSample{.confirm = true}};
  const RuntimeControls record{{}, false, true};
  require(advance_field_runtime(world, rt, tick, {}, screen.target).status ==
          RuntimeStatus::Rendered);
  require(rt.manual.area == 0 && rt.manual.player.x == 1 &&
          rt.manual.player.y == 1 && rt.discoveries.count == 0);

  // Every coordinate below is reached by ordinary controller input:
  // no direct player-position, pending-trigger or clock injection.
  for (int expected_x = 2; expected_x <= 3; ++expected_x) {
    tick += step;
    const RuntimeFrame moved = advance_field_runtime(
        world, rt, tick, right, screen.target);
    require(moved.status == RuntimeStatus::Rendered &&
            rt.manual.player.x == expected_x &&
            rt.manual.player.y == 1 &&
            rt.manual.pending == Trigger::None);
  }
  tick += step;
  require(advance_field_runtime(world, rt, tick, inspect, screen.target).
          inspected == Trigger::Event);
  tick += step;
  const RuntimeFrame first = advance_field_runtime(
      world, rt, tick, record, screen.target);
  require(first.status == RuntimeStatus::Rendered && first.clue_recorded &&
          first.clue_count == 1 &&
          rt.discoveries.entries[0].area == 0 &&
          rt.discoveries.entries[0].x == 4 &&
          rt.discoveries.entries[0].y == 1);

  // x3,y1 -> x6,y5 via seven real movements, avoiding the
  // already-inspected event tile. The final R enters authored exit E.
  const char route_to_exit[] = "DDDRRDR";
  for (char direction : route_to_exit) {
    if (direction == '\0') break;
    tick += step;
    const RuntimeControls controls = direction == 'D' ? down : right;
    const RuntimeFrame moved = advance_field_runtime(
        world, rt, tick, controls, screen.target);
    require(moved.status == RuntimeStatus::Rendered &&
            !moved.changed_area && rt.manual.area == 0 &&
            rt.discoveries.count == 1);
  }
  require(rt.manual.player.x == 6 && rt.manual.player.y == 5 &&
          rt.manual.pending == Trigger::Exit &&
          rt.manual.clock.paused_for_trigger);
  tick += step;
  const RuntimeFrame crossed = advance_field_runtime(
      world, rt, tick, inspect, screen.target);
  require(crossed.status == RuntimeStatus::Rendered &&
          crossed.changed_area && rt.manual.area == 1 &&
          rt.manual.pending == Trigger::None &&
          rt.manual.player.x == 1 && rt.manual.player.y == 1 &&
          rt.discoveries.count == 1);

  // In area 1 travel x1,y1 -> x4,y2 with RRRD. This puts the
  // authored second clue at x4,y3 directly AHEAD, facing Down.
  const char route_to_clue[] = "RRRD";
  for (char direction : route_to_clue) {
    if (direction == '\0') break;
    tick += step;
    const RuntimeControls controls = direction == 'D' ? down : right;
    const RuntimeFrame moved = advance_field_runtime(
        world, rt, tick, controls, screen.target);
    require(moved.status == RuntimeStatus::Rendered &&
            !moved.changed_area && rt.manual.area == 1 &&
            rt.manual.pending == Trigger::None);
  }
  require(rt.manual.player.x == 4 && rt.manual.player.y == 2 &&
          rt.manual.player.facing == Direction::Down &&
          rt.manual.player.successful_moves == 13);
  tick += step;
  require(advance_field_runtime(world, rt, tick, inspect, screen.target).
          inspected == Trigger::Event);
  tick += step;
  const RuntimeFrame second = advance_field_runtime(
      world, rt, tick, record, screen.target);
  require(second.status == RuntimeStatus::Rendered &&
          second.clue_recorded && second.clue_count == 2 &&
          rt.discoveries.entries[1].area == 1 &&
          rt.discoveries.entries[1].x == 4 &&
          rt.discoveries.entries[1].y == 3);

  // Stage 320: close the loop with *real* controls. Avoid stepping
  // on the area-1 event tile at (4,3); route around it via x2,y5.
  // Nine steps: (4,2) -> (2,2) -> (2,5) -> (6,5) exit.
  const RuntimeControls left{PadSample{.dpad_left = true}};
  const char route_back_to_exit[] = "LLDDDRRRR";
  for (char direction : route_back_to_exit) {
    if (direction == '\0') break;
    tick += step;
    const RuntimeControls controls = direction == 'L' ? left :
                                     direction == 'D' ? down : right;
    const RuntimeFrame moved = advance_field_runtime(
        world, rt, tick, controls, screen.target);
    require(moved.status == RuntimeStatus::Rendered &&
            !moved.changed_area && rt.manual.area == 1 &&
            rt.discoveries.count == 2);
  }
  require(rt.manual.player.x == 6 && rt.manual.player.y == 5 &&
          rt.manual.pending == Trigger::Exit &&
          rt.manual.clock.paused_for_trigger &&
          rt.manual.player.successful_moves == 22);
  tick += step;
  const RuntimeFrame returned = advance_field_runtime(
      world, rt, tick, inspect, screen.target);
  require(returned.status == RuntimeStatus::Rendered &&
          returned.changed_area && rt.manual.area == 0 &&
          rt.manual.pending == Trigger::None &&
          rt.manual.player.x == 1 && rt.manual.player.y == 1 &&
          rt.discoveries.count == 2);

  // Revisiting the original area-0 marker must not award clue #3.
  for (int target_x = 2; target_x <= 3; ++target_x) {
    tick += step;
    require(advance_field_runtime(
        world, rt, tick, right, screen.target).status ==
            RuntimeStatus::Rendered);
    require(rt.manual.player.x == target_x &&
            rt.manual.player.y == 1 &&
            rt.manual.pending == Trigger::None);
  }
  require(rt.manual.player.successful_moves == 24 &&
          rt.manual.player.facing == Direction::Right);
  tick += step;
  const RuntimeFrame revisited = advance_field_runtime(
      world, rt, tick, inspect, screen.target);
  require(revisited.inspected == Trigger::Event &&
          rt.discoveries.count == 2);
  tick += step;
  const RuntimeFrame duplicate = advance_field_runtime(
      world, rt, tick, record, screen.target);
  require(duplicate.status == RuntimeStatus::Rendered &&
          !duplicate.clue_recorded &&
          duplicate.clue_already_recorded &&
          duplicate.clue_count == 2 &&
          rt.discoveries.count == 2 &&
          rt.discoveries.entries[0].area == 0 &&
          rt.discoveries.entries[1].area == 1);

  // Confirm rendered rows in stable discovery order.
  const RuntimeControls view{{}, false, false, false, false, true};
  tick += step;
  const RuntimeFrame opened = advance_field_runtime(
      world, rt, tick, view, screen.target);
  require(opened.status == RuntimeStatus::Rendered &&
          opened.journal_visible && opened.clue_count == 2);
  constexpr int glyph_x = kJournalPanelX + 36 + 2; // 'A' top row
  constexpr int glyph_y = kJournalPanelY + 88;
  require(screen.pixel(glyph_x, glyph_y) == rgba(246, 247, 252));
  require(screen.pixel(glyph_x, glyph_y + 27) == rgba(246, 247, 252));

  // Neither quicksave nor quickload serializes the session journal.
  const RuntimeControls save{{}, false, false, true, false};
  const RuntimeControls load{{}, false, false, false, true};
  tick += step;
  require(advance_field_runtime(world, rt, tick, save, screen.target).
          snapshot_stored);
  tick += step;
  require(advance_field_runtime(world, rt, tick, load, screen.target).
          snapshot_restored);
  require(rt.discoveries.count == 2 &&
          valid_discovery_journal(world, rt.discoveries));

  // A fresh runtime starts a new ledger; the old save is still v1 world
  // state only and cannot import these volatile session clues.
  FieldRuntime fresh = start_field_runtime(world, kSwitchTicksPerSecond, 0);
  require(fresh.discoveries.count == 0 && fresh.manual.area == 0);
  screen.assert_guards();
}

} // namespace
int main() {
  test_sixty_hz_manual_event_pause_and_acknowledgment();
  test_manual_adjacent_inspection_renders_timed_outline();
  test_manual_inspection_caption_and_stale_target_invalidation();
  test_caption_kind_guard_and_exit_glyphs();
  test_manual_event_clue_recording_is_explicit_and_unique();
  test_b_does_not_record_without_inspected_event();
  test_simultaneous_A_and_B_cannot_collect_before_inspection();
  test_modal_save_load_and_demo_cannot_replay_held_A();
  test_held_journal_freezes_inputs_and_shows_session_clues();
  test_l_held_journal_freezes_inspection_timeout();
  test_manual_preflight_rejects_corrupt_ledger_without_L();
  test_journal_releases_old_partial_movement_cadence();
  test_l_modal_does_not_replay_held_A_on_release();
  test_cross_area_discovery_journal_survives_world_and_snapshot_changes();
  test_invalid_input_is_transactional_and_guarded();
  test_autoplay_exit_rejects_corrupt_discoveries_transactionally();
  test_autoplay_timing_checkpoints_and_manual_cancel();
  test_quicksave_restore_manual_mode_and_autoplay_isolation();
  test_quicksave_pending_event_restores_pause_and_status();
}
