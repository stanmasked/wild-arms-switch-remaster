// Stage 359: isolated battle journal crash/CRC tests; no Switch hardware.
#include "field_battle_file.hpp"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <unistd.h>
using namespace wa::field;
namespace {
struct Temp {
  char dir[64]="/tmp/wa-battle-XXXXXX";
  std::string base;
  Temp(){assert(::mkdtemp(dir));base=std::string(dir)+"/battle";}
  ~Temp(){
    for(const char* suf:{".a",".b",".a.tmp",".b.tmp",".field.a"})
      (void)std::remove((base+suf).c_str());
    (void)::rmdir(dir);
  }
};
BattleProgress progress(unsigned wins) {
  BattleProgress p{};
  p.history.victories=wins;
  p.history.last=wins?BattleResolution::Victory:BattleResolution::None;
  p.rewards.experience=8*wins;p.rewards.gella=12*wins;
  return p;
}
void equal(const BattleProgress& p,const BattleProgress& q){
  assert(p.history.victories==q.history.victories);
  assert(p.history.defeats==q.history.defeats);
  assert(p.history.retreats==q.history.retreats);
  assert(p.history.last==q.history.last);
  assert(p.rewards.experience==q.rewards.experience);
  assert(p.rewards.gella==q.rewards.gella);
}
void tamper(const std::string& path,std::size_t offset) {
  auto* f=std::fopen(path.c_str(),"r+b");assert(f);
  assert(std::fseek(f,static_cast<long>(offset),SEEK_SET)==0);
  const int old=std::fgetc(f);assert(old!=EOF);
  assert(std::fseek(f,static_cast<long>(offset),SEEK_SET)==0);
  assert(std::fputc(old^0x80,f)!=EOF);assert(std::fclose(f)==0);
}
void test_normal_two_generations_and_partial_temp(){
  Temp t;auto live=progress(5);
  assert(load_battle_progress_file(t.base,live).status==BattleJournalStatus::Missing);
  equal(live,progress(5));
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  assert(store_battle_progress_file(progress(2),t.base)==BattleJournalStatus::Stored);
  auto read=load_battle_progress_file(t.base,live);
  assert(read.status==BattleJournalStatus::Loaded&&!read.degraded&&read.generation==2);
  equal(live,progress(2));
  assert(store_battle_progress_file(progress(3),t.base,
    BattleJournalInterruption::AfterShortTemporary)==BattleJournalStatus::IoError);
  assert(load_battle_progress_file(t.base,live).generation==2);
  equal(live,progress(2));
  assert(store_battle_progress_file(progress(3),t.base,
    BattleJournalInterruption::AfterTemporarySynced)==BattleJournalStatus::IoError);
  assert(load_battle_progress_file(t.base,live).generation==2);
  equal(live,progress(2));
}
void test_removed_older_slot_and_post_rename_crash(){
  Temp t;auto live=progress(0);
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  assert(store_battle_progress_file(progress(2),t.base)==BattleJournalStatus::Stored);
  assert(store_battle_progress_file(progress(3),t.base,
    BattleJournalInterruption::AfterTargetRemoved)==BattleJournalStatus::IoError);
  auto read=load_battle_progress_file(t.base,live);
  assert(read.status==BattleJournalStatus::Loaded&&read.generation==2);
  equal(live,progress(2));
  assert(store_battle_progress_file(progress(3),t.base,
    BattleJournalInterruption::AfterRenamed)==BattleJournalStatus::IoError);
  read=load_battle_progress_file(t.base,live);
  assert(read.status==BattleJournalStatus::Loaded&&read.generation==3);
  equal(live,progress(3)); // Renamed may be committed despite failure.
}
void test_corrupt_latest_recovers_older_and_repairs(){
  Temp t;auto live=progress(4);
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  assert(store_battle_progress_file(progress(2),t.base)==BattleJournalStatus::Stored);
  tamper(t.base+".b",45);
  auto result=load_battle_progress_file(t.base,live);
  assert(result.status==BattleJournalStatus::Loaded);
  assert(result.generation==1&&result.degraded);
  equal(live,progress(1));
  assert(store_battle_progress_file(progress(3),t.base)==BattleJournalStatus::Stored);
  result=load_battle_progress_file(t.base,live);
  assert(result.status==BattleJournalStatus::Loaded&&!result.degraded);
  assert(result.generation==2);
  equal(live,progress(3));
}
void test_both_invalid_never_mutate_live_or_overwrite(){
  Temp t;auto live=progress(5);
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  tamper(t.base+".a",24);
  assert(load_battle_progress_file(t.base,live).status==BattleJournalStatus::Corrupt);
  equal(live,progress(5));
  assert(store_battle_progress_file(progress(2),t.base)==BattleJournalStatus::Corrupt);
  assert(read_battle_journal_slot(t.base+".a").status==BattleJournalStatus::Corrupt);
}
void test_length_magic_extra_bytes_and_crc(){
  Temp t;auto live=progress(7);
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  auto* f=std::fopen((t.base+".a").c_str(),"ab");assert(f);
  assert(std::fputc(0xDD,f)!=EOF);assert(std::fclose(f)==0);
  assert(load_battle_progress_file(t.base,live).status==BattleJournalStatus::Corrupt);
  equal(live,progress(7));
  f=std::fopen((t.base+".a").c_str(),"wb");assert(f);
  assert(std::fwrite("WABJ",1,4,f)==4);assert(std::fclose(f)==0);
  assert(load_battle_progress_file(t.base,live).status==BattleJournalStatus::Corrupt);
  equal(live,progress(7));
}
void test_invalid_state_generation_max_and_separate_field_save(){
  Temp t;
  auto bad=progress(1);bad.history.last=BattleResolution::None;
  assert(store_battle_progress_file(bad,t.base)==
         BattleJournalStatus::InvalidProgress);
  const std::string sentinel=t.base+".field.a";
  constexpr char field[]="WAFS-sentinel-unchanged";
  auto* f=std::fopen(sentinel.c_str(),"wb");assert(f);
  assert(std::fwrite(field,1,sizeof(field),f)==sizeof(field));
  assert(std::fclose(f)==0);
  assert(store_battle_progress_file(progress(1),t.base)==BattleJournalStatus::Stored);
  char restored[sizeof(field)]{};
  f=std::fopen(sentinel.c_str(),"rb");assert(f);
  assert(std::fread(restored,1,sizeof(restored),f)==sizeof(restored));
  assert(std::fclose(f)==0);
  assert(std::memcmp(restored,field,sizeof(field))==0);
  auto a=read_battle_journal_slot(t.base+".a");
  assert(a.status==BattleJournalStatus::Loaded);
  save_put_u64(a.raw.data()+4,std::numeric_limits<std::uint64_t>::max());
  save_put_u32(a.raw.data()+48,save_crc32(a.raw.data(),48));
  f=std::fopen((t.base+".a").c_str(),"wb");assert(f);
  assert(std::fwrite(a.raw.data(),1,a.raw.size(),f)==a.raw.size());
  assert(std::fclose(f)==0);
  assert(store_battle_progress_file(progress(2),t.base)==
         BattleJournalStatus::SequenceExhausted);
}
}
int main(){
 test_normal_two_generations_and_partial_temp();
 test_removed_older_slot_and_post_rename_crash();
 test_corrupt_latest_recovers_older_and_repairs();
 test_both_invalid_never_mutate_live_or_overwrite();
 test_length_magic_extra_bytes_and_crc();
 test_invalid_state_generation_max_and_separate_field_save();
}
