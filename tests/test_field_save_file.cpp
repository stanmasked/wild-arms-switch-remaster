#include "field_save_file.hpp"
#include "field_runtime.hpp"
#include <vector>

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace {
using namespace wa::field;
void expect(bool v) { if (!v) std::abort(); }
void same(const WorldState& a, const WorldState& b) {
  expect(a.area == b.area && a.pending == b.pending &&
         a.player.x == b.player.x && a.player.y == b.player.y &&
         a.player.facing == b.player.facing &&
         a.player.successful_moves == b.player.successful_moves &&
         a.clock.cadence_ms == b.clock.cadence_ms &&
         a.clock.carry_ms == b.clock.carry_ms &&
         a.clock.held == b.clock.held &&
         a.clock.paused_for_trigger == b.clock.paused_for_trigger &&
         a.decoder.confirm_down == b.decoder.confirm_down);
}
struct Fixture {
  char name[80] = "/tmp/wild-arms-stage294-XXXXXX";
  std::string prefix;
  Fixture() {
    char* dir = mkdtemp(name);
    expect(dir != nullptr);
    prefix = std::string(dir) + "/save";
  }
  ~Fixture() {
    for (const char* suffix : {".a", ".b", ".a.tmp", ".b.tmp"}) {
      const std::string file = prefix + suffix;
      (void)std::remove(file.c_str());
    }
    (void)rmdir(name);
  }
};
WorldState to_event(const FieldWorld& world) {
  WorldState s = start_world(world);
  for (int i = 0; i < 3; ++i) {
    const auto r = advance_world_frame(
        world, s, PadSample{.dpad_right = true}, 160);
    expect(r.controller.movement.successful_steps == 1);
  }
  expect(s.pending == Trigger::Event);
  return s;
}
void test_no_file_and_persistent_generation_round_trip() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  WorldState read = start_world(world);
  read.player.successful_moves = 90;
  const WorldState before = read;
  expect(load_field_save_file(world, f.prefix, read) ==
         FileSaveStatus::Missing);
  same(before, read);

  WorldState start = start_world(world);
  expect(store_field_save_file(world, start, f.prefix) ==
         FileSaveStatus::Stored);
  const FileSaveSlot a = read_field_journal_slot(world, f.prefix + ".a");
  expect(a.status == FileSaveStatus::Loaded && a.generation == 1);
  expect(load_field_save_file(world, f.prefix, read) ==
         FileSaveStatus::Loaded);
  same(start, read);

  const WorldState event = to_event(world);
  expect(store_field_save_file(world, event, f.prefix) ==
         FileSaveStatus::Stored);
  expect(read_field_journal_slot(world, f.prefix + ".b").generation == 2);
  expect(load_field_save_file(world, f.prefix, read) ==
         FileSaveStatus::Loaded);
  same(event, read);

  WorldState acknowledged = event;
  expect(advance_world_frame(world, acknowledged,
        PadSample{.confirm = true},160).controller.outcome ==
         PadFrameOutcome::Acknowledged);
  expect(store_field_save_file(world, acknowledged, f.prefix) ==
         FileSaveStatus::Stored);
  expect(read_field_journal_slot(world, f.prefix + ".a").generation == 3);
  expect(load_field_save_file(world, f.prefix, read) ==
         FileSaveStatus::Loaded);
  same(acknowledged, read);
}

void test_corrupt_latest_falls_back_to_previous_save() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  WorldState first = start_world(world);
  const WorldState second = to_event(world);
  expect(store_field_save_file(world, first, f.prefix) ==
         FileSaveStatus::Stored);
  expect(store_field_save_file(world, second, f.prefix) ==
         FileSaveStatus::Stored);
  {
    std::FILE* fp = std::fopen((f.prefix + ".b").c_str(), "r+b");
    expect(fp != nullptr);
    expect(std::fseek(fp, 15, SEEK_SET) == 0);
    expect(std::fputc(0xFF,fp) != EOF);
    expect(std::fclose(fp) == 0);
  }
  WorldState received = second;
  expect(load_field_save_file(world, f.prefix, received) ==
         FileSaveStatus::Loaded);
  same(first, received);
  // Malformed newer slot never replaces good older generation.
  expect(store_field_save_file(world, second, f.prefix) ==
         FileSaveStatus::Stored);
  expect(load_field_save_file(world, f.prefix, received) ==
         FileSaveStatus::Loaded);
  same(second, received);
}

void test_degraded_journal_warning_and_redundancy_repair() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  const WorldState start = start_world(world);
  const WorldState event = to_event(world);
  WorldState out = event;
  auto initial = load_field_save_file_detailed(world,f.prefix,out);
  expect(initial.status == FileSaveStatus::Missing && !initial.degraded);
  same(event,out);
  expect(store_field_save_file(world,start,f.prefix)==FileSaveStatus::Stored);
  auto one = load_field_save_file_detailed(world,f.prefix,out);
  expect(one.status == FileSaveStatus::Loaded &&
         !one.degraded && one.selected_generation == 1);
  same(start,out);
  expect(store_field_save_file(world,event,f.prefix)==FileSaveStatus::Stored);
  auto both = load_field_save_file_detailed(world,f.prefix,out);
  expect(both.status == FileSaveStatus::Loaded &&
         !both.degraded && both.selected_generation == 2);
  same(event,out);

  // A committed generation is torn; older intact generation is recovered.
  {
    std::FILE* fp=std::fopen((f.prefix+".b").c_str(),"wb");
    expect(fp!=nullptr);
    expect(std::fwrite("WAJ1",1,4,fp)==4);
    expect(std::fclose(fp)==0);
  }
  auto fallback = load_field_save_file_detailed(world,f.prefix,out);
  expect(fallback.status == FileSaveStatus::Loaded &&
         fallback.degraded && fallback.selected_generation == 1);
  same(start,out);

  // A normal save heals the bad backup without damaging the good one.
  expect(store_field_save_file(world,event,f.prefix)==FileSaveStatus::Stored);
  auto healed=load_field_save_file_detailed(world,f.prefix,out);
  expect(healed.status == FileSaveStatus::Loaded &&
         !healed.degraded && healed.selected_generation == 2);
  same(event,out);

  // Damage the *older* backup: load the newer intact version but warn,
  // because the pair no longer offers a usable fallback generation.
  {
    std::FILE* fp=std::fopen((f.prefix+".a").c_str(),"r+b");
    expect(fp!=nullptr);
    expect(std::fseek(fp,20,SEEK_SET)==0);
    expect(std::fputc(0xA5,fp)!=EOF);
    expect(std::fclose(fp)==0);
  }
  auto degraded=load_field_save_file_detailed(world,f.prefix,out);
  expect(degraded.status == FileSaveStatus::Loaded &&
         degraded.degraded && degraded.selected_generation == 2);
  same(event,out);

  // Invalid journal data never mutates the caller, even when both
  // generations are compromised.
  {
    std::FILE* fp=std::fopen((f.prefix+".b").c_str(),"wb");
    expect(fp!=nullptr);
    expect(std::fwrite("torn",1,4,fp)==4);
    expect(std::fclose(fp)==0);
  }
  out=start;
  auto corrupt=load_field_save_file_detailed(world,f.prefix,out);
  expect(corrupt.status == FileSaveStatus::Corrupt &&
         !corrupt.degraded && corrupt.selected_generation == 0);
  same(start,out);
}

void test_stale_temporary_is_not_published_and_failed_publish_keeps_old() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  WorldState old = start_world(world);
  WorldState changed = to_event(world);
  expect(store_field_save_file(world, old, f.prefix) ==
         FileSaveStatus::Stored);
  {
    std::ofstream stale(f.prefix + ".b.tmp", std::ios::binary);
    stale << "interrupted operation";
  }
  WorldState observed = changed;
  expect(load_field_save_file(world, f.prefix, observed) ==
         FileSaveStatus::Loaded);
  same(old, observed);

  // An occupied directory blocks publication; the previous A stays valid.
  expect(::mkdir((f.prefix + ".b").c_str(), 0700) == 0);
  expect(store_field_save_file(world, changed, f.prefix) ==
         FileSaveStatus::IoError);
  expect(load_field_save_file(world, f.prefix, observed) ==
         FileSaveStatus::IoError);
  // Explicitly remove the bad test directory, then inspect last good save.
  expect(::rmdir((f.prefix + ".b").c_str()) == 0);
  expect(load_field_save_file(world, f.prefix, observed) ==
         FileSaveStatus::Loaded);
  same(old, observed);
}

void test_invalid_state_and_invalid_world_do_not_overwrite() {
  Fixture f;
  FieldWorld world = make_demo_world();
  WorldState original = start_world(world);
  expect(store_field_save_file(world, original, f.prefix) ==
         FileSaveStatus::Stored);
  WorldState bad = original;
  bad.area = -1;
  expect(store_field_save_file(world, bad, f.prefix) ==
         FileSaveStatus::InvalidState);
  FieldWorld wrong = world;
  wrong.areas[0].entrance_x = 0;
  expect(store_field_save_file(wrong, original, f.prefix) ==
         FileSaveStatus::InvalidWorld);
  WorldState check = bad;
  expect(load_field_save_file(world, f.prefix, check) ==
         FileSaveStatus::Loaded);
  same(original, check);
  wrong = world;
  wrong.areas[1].map.tiles[13] = '#';
  expect(wrong.valid());
  expect(load_field_save_file(wrong, f.prefix, check) ==
         FileSaveStatus::Corrupt);
  same(original,check);
}

void test_io_error_and_generation_exhaustion() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  WorldState s = start_world(world);
  const std::string impossible = f.prefix + "/missing_child";
  expect(store_field_save_file(world, s, impossible) ==
         FileSaveStatus::IoError);
  expect(load_field_save_file(world, impossible, s) ==
         FileSaveStatus::Missing);
  expect(store_field_save_file(world, s, f.prefix) ==
         FileSaveStatus::Stored);
  FieldSaveRecord rec{};
  expect(encode_field_save(world,s,rec) == FieldSaveStatus::Encoded);
  FieldJournalBytes blob{};
  blob[0]='W';blob[1]='A';blob[2]='J';blob[3]='1';
  save_put_u64(blob.data()+4,std::numeric_limits<std::uint64_t>::max());
  for(std::size_t i=0;i<rec.size();++i)blob[12+i]=rec[i];
  save_put_u32(blob.data()+52,save_crc32(blob.data(),52));
  {
    std::FILE* fp=std::fopen((f.prefix+".a").c_str(),"wb");
    expect(fp!=nullptr);
    expect(std::fwrite(blob.data(),1,blob.size(),fp)==blob.size());
    expect(std::fclose(fp)==0);
  }
  expect(store_field_save_file(world,s,f.prefix) ==
         FileSaveStatus::SequenceExhausted);
}

// Simulated power-cut windows must not make a previous *committed*
// generation disappear. Only a complete, renamed journal is loadable.
void test_interrupted_journal_publication_recovery() {
  const FieldWorld world = make_demo_world();
  const WorldState initial = start_world(world);
  const WorldState event = to_event(world);
  const JournalInterruption points[] = {
    JournalInterruption::AfterShortTemporaryWrite,
    JournalInterruption::AfterTemporarySynced,
    JournalInterruption::AfterTemporaryValidated,
    JournalInterruption::AfterPreviousSlotRemoved,
    JournalInterruption::AfterNewSlotRenamed
  };
  for (const auto point : points) {
    Fixture f;
    expect(store_field_save_file(world, initial, f.prefix) ==
           FileSaveStatus::Stored);
    expect(store_field_save_file(world, event, f.prefix) ==
           FileSaveStatus::Stored);
    const FileSaveSlot latest = read_field_journal_slot(
        world, f.prefix + ".b");
    expect(latest.status == FileSaveStatus::Loaded &&
           latest.generation == 2);

    // The third write rotates to A, leaving B (generation 2) untouched.
    expect(store_field_save_file(world, initial, f.prefix, point) ==
           FileSaveStatus::IoError);

    const FileSaveSlot still_good = read_field_journal_slot(
        world, f.prefix + ".b");
    expect(still_good.status == FileSaveStatus::Loaded &&
           still_good.bytes == latest.bytes);
    expect(still_good.generation == 2);
    const FileSaveSlot target = read_field_journal_slot(
        world, f.prefix + ".a");
    const FileSaveSlot temporary = read_field_journal_slot(
        world, f.prefix + ".a.tmp");
    if (point == JournalInterruption::AfterNewSlotRenamed) {
      // Rename completed before the simulated crash, so generation 3
      // legitimately wins even if the writer didn't report success.
      expect(target.status == FileSaveStatus::Loaded &&
             target.generation == 3);
      expect(temporary.status == FileSaveStatus::Missing);
    } else {
      // The old generation 1 may survive, or be unlinked just before
      // rename; the latest generation 2 remains intact either way.
      expect(target.status == FileSaveStatus::Loaded ||
             target.status == FileSaveStatus::Missing);
      if (point == JournalInterruption::AfterShortTemporaryWrite)
        expect(temporary.status == FileSaveStatus::Corrupt);
      else
        expect(temporary.status == FileSaveStatus::Loaded &&
               temporary.generation == 3);
    }
    WorldState result = event;
    expect(load_field_save_file(world, f.prefix, result) ==
           FileSaveStatus::Loaded);
    if (point == JournalInterruption::AfterNewSlotRenamed)
      same(initial, result);
    else
      same(event, result);

    // A fresh application run overwrites stale .tmp, publishes a
    // verified next generation and loads it unambiguously.
    expect(store_field_save_file(world, initial, f.prefix) ==
           FileSaveStatus::Stored);
    expect(load_field_save_file(world, f.prefix, result) ==
           FileSaveStatus::Loaded);
    same(initial, result);
  }
}

void test_interrupted_first_save_never_accepts_temporary_file() {
  const FieldWorld world = make_demo_world();
  const WorldState initial = start_world(world);
  const JournalInterruption points[] = {
    JournalInterruption::AfterShortTemporaryWrite,
    JournalInterruption::AfterTemporarySynced,
    JournalInterruption::AfterTemporaryValidated,
    JournalInterruption::AfterPreviousSlotRemoved
  };
  for (const auto point : points) {
    Fixture f;
    expect(store_field_save_file(world, initial, f.prefix, point) ==
           FileSaveStatus::IoError);
    WorldState output = initial;
    output.player.successful_moves = 67;
    const WorldState marker = output;
    expect(load_field_save_file(world, f.prefix, output) ==
           FileSaveStatus::Missing);
    same(marker, output);
    expect(store_field_save_file(world, initial, f.prefix) ==
           FileSaveStatus::Stored);
    expect(load_field_save_file(world, f.prefix, output) ==
           FileSaveStatus::Loaded);
    same(initial, output);
  }
}

void test_restart_import_matches_event_frame_and_confirm_edge() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  constexpr std::uint64_t frequency = 19200000;
  constexpr std::uint64_t step = 3072000; // 160ms @ 19.2MHz
  const PixelTarget render_target{};
  (void)render_target;
  std::vector<std::uint32_t> pixels(
      static_cast<std::size_t>(kRasterWidth) * kRasterHeight);
  PixelTarget target{pixels.data(), kRasterWidth, kRasterHeight,
                     kRasterWidth};
  FieldRuntime first = start_field_runtime(world, frequency, 0);
  expect(advance_field_runtime(world, first, 0, {}, target).status ==
         RuntimeStatus::Rendered);
  const RuntimeControls right{PadSample{.dpad_right = true}};
  for(int frame=1; frame<=3; ++frame)
    expect(advance_field_runtime(world, first, step*frame,
                                 right, target).status ==
           RuntimeStatus::Rendered);
  expect(first.manual.pending == Trigger::Event);
  expect(first.manual.player.x == 4);
  const auto reference_event = pixels;

  const RuntimeControls save{{}, false, false, true, false};
  expect(advance_field_runtime(world, first, step*4,
                               save, target).snapshot_stored);
  expect(pixels == reference_event);
  expect(store_field_save_file(world, first.quicksave.world,
                               f.prefix) == FileSaveStatus::Stored);

  // This represents a full process restart: fresh RAM state, no quicksave.
  FieldRuntime restarted =
      start_field_runtime(world, frequency, step*4);
  expect(!restarted.quicksave.occupied);
  WorldState imported{};
  expect(load_field_save_file(world, f.prefix, imported) ==
         FileSaveStatus::Loaded);
  restarted.quicksave.world = imported;
  restarted.quicksave.occupied = true;
  const RuntimeControls load{{}, false, false, false, true};
  const RuntimeFrame loaded = advance_field_runtime(
      world, restarted, step*4, load, target);
  expect(loaded.status == RuntimeStatus::Rendered &&
         loaded.snapshot_restored);
  expect(pixels == reference_event);
  expect(restarted.manual.pending == Trigger::Event);
  const RuntimeControls ack{PadSample{.confirm = true}};
  const auto after_ack = advance_field_runtime(
      world, restarted, step*5, ack, target);
  expect(after_ack.status == RuntimeStatus::Rendered);
  expect(restarted.manual.pending == Trigger::None);
  expect(pixels != reference_event);
  const auto reload = advance_field_runtime(
      world, restarted, step*6, load, target);
  expect(reload.snapshot_restored &&
         restarted.manual.pending == Trigger::Event);
  expect(pixels == reference_event);
}
void test_per_open_readback_evidence_is_structural_only() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  const WorldState original = start_world(world);
  expect(store_field_save_file(world,original,f.prefix) == FileSaveStatus::Stored);
  JournalReadDiagnostic good{};
  const FileSaveSlot valid =
      read_field_journal_slot(world,f.prefix+".a",&good);
  expect(valid.status == FileSaveStatus::Loaded);
  expect(good.bytes_read == kFieldJournalBytes && good.eof_after_probe);
  expect(!good.extra_byte && !good.stream_error && good.closed_ok);
  expect(good.header_ok && good.crc_ok && good.decoded_ok);

  // A short record must be diagnosed as a size failure, not as a
  // mismatched world or an invented bad CRC.
  {
    std::FILE* file=std::fopen((f.prefix+".a").c_str(),"wb");
    expect(file!=nullptr);
    expect(std::fwrite("WAJ1",1,4,file)==4);
    expect(std::fclose(file)==0);
  }
  JournalReadDiagnostic short_read{};
  const auto short_slot =
      read_field_journal_slot(world,f.prefix+".a",&short_read);
  expect(short_slot.status==FileSaveStatus::Corrupt);
  expect(short_read.bytes_read==4 && short_read.eof_after_probe);
  expect(!short_read.header_ok && !short_read.crc_ok);

  // Restore a valid record and corrupt payload without updating its CRC.
  expect(store_field_save_file(world,original,f.prefix) == FileSaveStatus::Stored);
  {
    std::FILE* file=std::fopen((f.prefix+".a").c_str(),"r+b");
    expect(file!=nullptr);
    expect(std::fseek(file,23,SEEK_SET)==0);
    expect(std::fputc(0xA5,file)!=EOF);
    expect(std::fclose(file)==0);
  }
  JournalReadDiagnostic bad_crc{};
  const auto rejected =
      read_field_journal_slot(world,f.prefix+".a",&bad_crc);
  expect(rejected.status==FileSaveStatus::Corrupt);
  expect(bad_crc.bytes_read==kFieldJournalBytes);
  expect(bad_crc.header_ok && !bad_crc.crc_ok && !bad_crc.decoded_ok);
}

void test_write_diagnostic_lifecycle_and_corrupt_slot_repair() {
  Fixture f;
  const FieldWorld world = make_demo_world();
  const WorldState start = start_world(world);
  const WorldState event = to_event(world);
  JournalWriteDiagnostic audit{};
  expect(store_field_save_file(
      world,start,f.prefix,JournalInterruption::None,&audit) ==
      FileSaveStatus::Stored);
  expect(audit.step == JournalWriteStep::VerifiedCommitted);
  expect(audit.existing_a == FileSaveStatus::Missing &&
         audit.existing_b == FileSaveStatus::Missing);
  expect(audit.temporary_status == FileSaveStatus::Loaded &&
         audit.published_status == FileSaveStatus::Loaded);
  expect(audit.intended_generation == 1 && audit.read_attempts == 1 &&
         audit.rename_succeeded && audit.published_bytes_equal);

  expect(store_field_save_file(world,event,f.prefix) ==
         FileSaveStatus::Stored);
  {
    std::FILE* fp=std::fopen((f.prefix+".b").c_str(),"r+b");
    expect(fp!=nullptr);
    expect(std::fseek(fp,23,SEEK_SET)==0);
    expect(std::fputc(0xFF,fp)!=EOF);
    expect(std::fclose(fp)==0);
  }
  expect(store_field_save_file(
      world,start,f.prefix,JournalInterruption::None,&audit) ==
      FileSaveStatus::Stored);
  expect(audit.step == JournalWriteStep::VerifiedCommitted &&
         audit.existing_a == FileSaveStatus::Loaded &&
         audit.existing_b == FileSaveStatus::Corrupt &&
         audit.intended_generation == 2);
  expect(audit.published_bytes_equal && audit.read_attempts > 0);

  // The audit may observe a blocked path but may never claim the record
  // is published. No valid save is overwritten by the test.
  expect(::mkdir((f.prefix+".a.tmp").c_str(),0700)==0);
  expect(store_field_save_file(
      world,event,f.prefix,JournalInterruption::None,&audit) ==
      FileSaveStatus::IoError);
  expect(audit.step == JournalWriteStep::PreviousSlotsRead ||
         audit.step == JournalWriteStep::TemporaryOpened);
  expect(::rmdir((f.prefix+".a.tmp").c_str())==0);
}

void test_postpublish_false_negative_error_reports() {
  Fixture f;
  const FieldWorld world=make_demo_world();
  const WorldState start=start_world(world);
  const WorldState event=to_event(world);
  expect(store_field_save_file(world,start,f.prefix)==FileSaveStatus::Stored);
  // A transient failure to open the freshly published file must be
  // retried; only an exact CRC-valid published payload can pass.
  expect(store_field_save_file(
      world,event,f.prefix,
      JournalInterruption::AfterPostPublishFirstReadRejected)==
      FileSaveStatus::Stored);
  const FileSaveSlot b=read_field_journal_slot(world,f.prefix+".b");
  expect(b.status==FileSaveStatus::Loaded && b.generation==2);
  same(event,b.world);
  // An emulated false-negative rename result with a valid committed file
  // is also not a data loss. This test makes no claim about hardware fsync.
  expect(store_field_save_file(
      world,start,f.prefix,
      JournalInterruption::AfterNewSlotRenamedReportedFailure)==
      FileSaveStatus::Stored);
  const FileSaveSlot a=read_field_journal_slot(world,f.prefix+".a");
  expect(a.status==FileSaveStatus::Loaded && a.generation==3);
  same(start,a.world);
  WorldState loaded{};
  expect(load_field_save_file(world,f.prefix,loaded)==FileSaveStatus::Loaded);
  same(start,loaded);
}

void test_postpublish_never_accepts_blocked_destination() {
  Fixture f;
  const FieldWorld world=make_demo_world();
  const WorldState start=start_world(world);
  const WorldState event=to_event(world);
  expect(store_field_save_file(world,start,f.prefix)==FileSaveStatus::Stored);
  expect(::mkdir((f.prefix+".b").c_str(),0700)==0);
  expect(store_field_save_file(
      world,event,f.prefix,
      JournalInterruption::AfterNewSlotRenamedReportedFailure)==
      FileSaveStatus::IoError);
  expect(::rmdir((f.prefix+".b").c_str())==0);
  WorldState loaded{};
  expect(load_field_save_file(world,f.prefix,loaded)==FileSaveStatus::Loaded);
  same(start,loaded);
}

}

int main() {
  test_no_file_and_persistent_generation_round_trip();
  test_corrupt_latest_falls_back_to_previous_save();
  test_degraded_journal_warning_and_redundancy_repair();
  test_stale_temporary_is_not_published_and_failed_publish_keeps_old();
  test_invalid_state_and_invalid_world_do_not_overwrite();
  test_io_error_and_generation_exhaustion();
  test_restart_import_matches_event_frame_and_confirm_edge();
  test_interrupted_journal_publication_recovery();
  test_interrupted_first_save_never_accepts_temporary_file();
  test_per_open_readback_evidence_is_structural_only();
  test_write_diagnostic_lifecycle_and_corrupt_slot_repair();
  test_postpublish_false_negative_error_reports();
  test_postpublish_never_accepts_blocked_destination();
}
