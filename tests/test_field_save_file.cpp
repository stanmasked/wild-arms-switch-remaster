#include "field_save_file.hpp"

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
}

int main() {
  test_no_file_and_persistent_generation_round_trip();
  test_corrupt_latest_falls_back_to_previous_save();
  test_stale_temporary_is_not_published_and_failed_publish_keeps_old();
  test_invalid_state_and_invalid_world_do_not_overwrite();
  test_io_error_and_generation_exhaustion();
}
