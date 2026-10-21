#include "field_arm_reward_file.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>
#include <unistd.h>

using namespace wa::field;

namespace {
struct TempDir {
  char pattern[64]="/tmp/wa-arm-rewards-XXXXXX";
  std::string path;
  TempDir() {
    const char* made=::mkdtemp(pattern);
    assert(made!=nullptr);
    path=made;
  }
  ~TempDir() { std::filesystem::remove_all(path); }
  std::string base() const { return path+"/arm-rewards"; }
};

std::vector<std::uint8_t> read_bytes(const std::string& path) {
  std::ifstream file(path,std::ios::binary);
  assert(file.good());
  return std::vector<std::uint8_t>(
      std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>());
}
void write_bytes(const std::string& path,const std::vector<std::uint8_t>& bytes) {
  std::ofstream file(path,std::ios::binary|std::ios::trunc);
  assert(file.good());
  file.write(reinterpret_cast<const char*>(bytes.data()),
             static_cast<std::streamsize>(bytes.size()));
  file.close();
  assert(file.good());
}
void refresh_crc(ArmRewardJournalRecord& bytes) {
  save_put_u32(bytes.data()+28,save_crc32(bytes.data(),28));
}

void test_codec_roundtrip_and_atomic_rejection() {
  ArmRewardJournalRecord bytes{};
  assert(encode_arm_reward_record(7,{19,23},bytes)==
         ArmRewardRecordStatus::Encoded);
  assert(bytes[0]=='W' && bytes[1]=='A' && bytes[2]=='E' && bytes[3]=='R');
  assert(bytes[4]==1 && bytes[5]==0 && bytes[6]==0 && bytes[7]==0);
  assert(save_get_u64(bytes.data()+8)==7);
  assert(save_get_u32(bytes.data()+16)==19);
  assert(save_get_u32(bytes.data()+20)==23);
  assert(save_get_u32(bytes.data()+28)==save_crc32(bytes.data(),28));

  std::uint64_t generation=99;
  BattleRewardAccount rewards{1,2};
  assert(decode_arm_reward_record(bytes.data(),bytes.size(),generation,rewards)==
         ArmRewardRecordStatus::Decoded);
  assert(generation==7 && rewards.experience==19 && rewards.gella==23);

  auto bad=bytes;
  bad[0]='X';
  assert(decode_arm_reward_record(bad.data(),bad.size(),generation,rewards)==
         ArmRewardRecordStatus::InvalidMagic);
  assert(generation==7 && rewards.experience==19 && rewards.gella==23);

  bad=bytes;bad[4]=2;refresh_crc(bad);
  assert(decode_arm_reward_record(bad.data(),bad.size(),generation,rewards)==
         ArmRewardRecordStatus::UnsupportedVersion);
  bad=bytes;bad[5]=1;refresh_crc(bad);
  assert(decode_arm_reward_record(bad.data(),bad.size(),generation,rewards)==
         ArmRewardRecordStatus::Malformed);
  bad=bytes;bad[16]^=0x40;
  assert(decode_arm_reward_record(bad.data(),bad.size(),generation,rewards)==
         ArmRewardRecordStatus::InvalidChecksum);
  assert(decode_arm_reward_record(bytes.data(),bytes.size()-1,generation,rewards)==
         ArmRewardRecordStatus::InvalidLength);
  assert(encode_arm_reward_record(0,{4,5},bad)==
         ArmRewardRecordStatus::InvalidValues);
  assert(generation==7 && rewards.experience==19 && rewards.gella==23);
}

void test_two_slot_generations_and_cold_reload() {
  TempDir dir;
  BattleRewardAccount loaded{99,101};
  assert(load_arm_reward_file(dir.base(),loaded).status==
         ArmRewardJournalStatus::Missing);
  assert(loaded.experience==99 && loaded.gella==101);

  assert(store_arm_reward_file({8,12},dir.base())==
         ArmRewardJournalStatus::Stored);
  const auto generation_one=read_bytes(dir.base()+".a");
  assert(generation_one.size()==kArmRewardJournalBytes);
  assert(!std::filesystem::exists(dir.base()+".b"));
  auto result=load_arm_reward_file(dir.base(),loaded);
  assert(result.status==ArmRewardJournalStatus::Loaded &&
         result.generation==1 && !result.degraded);
  assert(loaded.experience==8 && loaded.gella==12);

  assert(store_arm_reward_file({16,24},dir.base())==
         ArmRewardJournalStatus::Stored);
  assert(read_bytes(dir.base()+".a")==generation_one);
  const auto generation_two=read_bytes(dir.base()+".b");
  result=load_arm_reward_file(dir.base(),loaded);
  assert(result.status==ArmRewardJournalStatus::Loaded &&
         result.generation==2 && loaded.experience==16 && loaded.gella==24);

  assert(store_arm_reward_file({24,36},dir.base())==
         ArmRewardJournalStatus::Stored);
  assert(read_bytes(dir.base()+".b")==generation_two);
  result=load_arm_reward_file(dir.base(),loaded);
  assert(result.status==ArmRewardJournalStatus::Loaded &&
         result.generation==3 && loaded.experience==24 && loaded.gella==36);
}

void test_interrupted_replacement_keeps_a_valid_generation() {
  for (const auto point : {
      ArmRewardJournalInterruption::AfterShortTemporary,
      ArmRewardJournalInterruption::AfterTemporarySynced,
      ArmRewardJournalInterruption::AfterTemporaryValidated,
      ArmRewardJournalInterruption::AfterTargetRemoved,
      ArmRewardJournalInterruption::AfterRenamed}) {
    TempDir dir;
    assert(store_arm_reward_file({8,12},dir.base())==
           ArmRewardJournalStatus::Stored);
    const auto first=read_bytes(dir.base()+".a");
    assert(store_arm_reward_file({16,24},dir.base(),point)==
           ArmRewardJournalStatus::IoError);
    BattleRewardAccount loaded{};
    const auto result=load_arm_reward_file(dir.base(),loaded);
    if (point==ArmRewardJournalInterruption::AfterRenamed) {
      assert(result.status==ArmRewardJournalStatus::Loaded &&
             result.generation==2);
      assert(loaded.experience==16 && loaded.gella==24);
    } else {
      assert(result.status==ArmRewardJournalStatus::Loaded &&
             result.generation==1);
      assert(loaded.experience==8 && loaded.gella==12);
      assert(read_bytes(dir.base()+".a")==first);
    }
  }
}

void test_corrupt_newest_falls_back_and_is_repaired() {
  TempDir dir;
  assert(store_arm_reward_file({8,12},dir.base())==
         ArmRewardJournalStatus::Stored);
  assert(store_arm_reward_file({16,24},dir.base())==
         ArmRewardJournalStatus::Stored);
  auto newest=read_bytes(dir.base()+".b");
  newest[16]^=0x01;
  write_bytes(dir.base()+".b",newest);

  BattleRewardAccount loaded{};
  auto result=load_arm_reward_file(dir.base(),loaded);
  assert(result.status==ArmRewardJournalStatus::Loaded &&
         result.generation==1 && result.degraded);
  assert(loaded.experience==8 && loaded.gella==12);

  assert(store_arm_reward_file({32,48},dir.base())==
         ArmRewardJournalStatus::Stored);
  result=load_arm_reward_file(dir.base(),loaded);
  assert(result.status==ArmRewardJournalStatus::Loaded &&
         result.generation==2 && !result.degraded);
  assert(loaded.experience==32 && loaded.gella==48);
}

void test_both_corrupt_slots_are_never_overwritten() {
  TempDir dir;
  write_bytes(dir.base()+".a",{1,2,3});
  write_bytes(dir.base()+".b",{4,5,6});
  const auto a=read_bytes(dir.base()+".a");
  const auto b=read_bytes(dir.base()+".b");
  BattleRewardAccount loaded{77,88};
  assert(load_arm_reward_file(dir.base(),loaded).status==
         ArmRewardJournalStatus::Corrupt);
  assert(loaded.experience==77 && loaded.gella==88);
  assert(store_arm_reward_file({100,200},dir.base())==
         ArmRewardJournalStatus::Corrupt);
  assert(read_bytes(dir.base()+".a")==a && read_bytes(dir.base()+".b")==b);
}

void test_generation_exhaustion_fails_closed() {
  TempDir dir;
  ArmRewardJournalRecord bytes{};
  assert(encode_arm_reward_record(
      std::numeric_limits<std::uint64_t>::max(),{8,12},bytes)==
      ArmRewardRecordStatus::Encoded);
  write_bytes(dir.base()+".a",
              std::vector<std::uint8_t>(bytes.begin(),bytes.end()));
  const auto before=read_bytes(dir.base()+".a");
  assert(store_arm_reward_file({16,24},dir.base())==
         ArmRewardJournalStatus::SequenceExhausted);
  assert(read_bytes(dir.base()+".a")==before);
}

} // namespace

int main() {
  test_codec_roundtrip_and_atomic_rejection();
  test_two_slot_generations_and_cold_reload();
  test_interrupted_replacement_keeps_a_valid_generation();
  test_corrupt_newest_falls_back_and_is_repaired();
  test_both_corrupt_slots_are_never_overwritten();
  test_generation_exhaustion_fails_closed();
  return 0;
}
