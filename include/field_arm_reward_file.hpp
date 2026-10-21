#pragma once
// Stage 404: separate dual-slot persistence for opt-in ARM prototype rewards.
// Never shares the WAFS field save or WABJ regular-battle journal.
#include "field_battle_rewards.hpp"
#include "field_save_codec.hpp"

#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <unistd.h>

namespace wa::field {

constexpr std::size_t kArmRewardJournalBytes = 32;
constexpr std::uint8_t kArmRewardJournalVersion = 1;
using ArmRewardJournalRecord = std::array<std::uint8_t,kArmRewardJournalBytes>;

enum class ArmRewardRecordStatus : std::uint8_t {
  Encoded, Decoded, InvalidValues, InvalidLength, InvalidMagic,
  UnsupportedVersion, InvalidChecksum, Malformed
};

enum class ArmRewardJournalStatus : std::uint8_t {
  Stored, Loaded, Missing, Corrupt, IoError, SequenceExhausted
};

enum class ArmRewardJournalInterruption : std::uint8_t {
  None, AfterShortTemporary, AfterTemporarySynced,
  AfterTemporaryValidated, AfterTargetRemoved, AfterRenamed
};

struct ArmRewardJournalSlot {
  ArmRewardJournalStatus status = ArmRewardJournalStatus::Missing;
  std::uint64_t generation = 0;
  BattleRewardAccount rewards{};
  ArmRewardJournalRecord bytes{};
};

struct ArmRewardJournalLoad {
  ArmRewardJournalStatus status = ArmRewardJournalStatus::Missing;
  bool degraded = false;
  std::uint64_t generation = 0;
};

// Exact 32-byte v1 layout:
// 0..3 WAER, 4 version, 5..7 reserved, 8..15 generation,
// 16..19 EXP, 20..23 Gella, 24..27 reserved, 28..31 CRC32(bytes 0..27).
// CRC32 detects accidental corruption; it is not a cryptographic signature.
[[nodiscard]] inline ArmRewardRecordStatus encode_arm_reward_record(
    std::uint64_t generation, const BattleRewardAccount& rewards,
    ArmRewardJournalRecord& output) noexcept {
  if (generation == 0) return ArmRewardRecordStatus::InvalidValues;
  ArmRewardJournalRecord next{};
  next[0]='W'; next[1]='A'; next[2]='E'; next[3]='R';
  next[4]=kArmRewardJournalVersion;
  save_put_u64(next.data()+8,generation);
  save_put_u32(next.data()+16,rewards.experience);
  save_put_u32(next.data()+20,rewards.gella);
  save_put_u32(next.data()+28,save_crc32(next.data(),28));
  output=next;
  return ArmRewardRecordStatus::Encoded;
}

[[nodiscard]] inline ArmRewardRecordStatus decode_arm_reward_record(
    const std::uint8_t* data, std::size_t size,
    std::uint64_t& generation, BattleRewardAccount& rewards) noexcept {
  if (!data || size!=kArmRewardJournalBytes)
    return ArmRewardRecordStatus::InvalidLength;
  if (data[0]!='W' || data[1]!='A' || data[2]!='E' || data[3]!='R')
    return ArmRewardRecordStatus::InvalidMagic;
  if (data[4]!=kArmRewardJournalVersion)
    return ArmRewardRecordStatus::UnsupportedVersion;
  if (data[5]!=0 || data[6]!=0 || data[7]!=0 ||
      data[24]!=0 || data[25]!=0 || data[26]!=0 || data[27]!=0)
    return ArmRewardRecordStatus::Malformed;
  if (save_crc32(data,28)!=save_get_u32(data+28))
    return ArmRewardRecordStatus::InvalidChecksum;
  const auto next_generation=save_get_u64(data+8);
  if (next_generation==0) return ArmRewardRecordStatus::InvalidValues;
  const BattleRewardAccount next{
      save_get_u32(data+16),save_get_u32(data+20)};
  generation=next_generation;
  rewards=next;
  return ArmRewardRecordStatus::Decoded;
}

[[nodiscard]] inline ArmRewardJournalSlot read_arm_reward_journal_slot(
    const std::string& path) noexcept {
  ArmRewardJournalSlot result{};
  errno=0;
  std::FILE* f=std::fopen(path.c_str(),"rb");
  if (!f) {
    result.status=errno==ENOENT ? ArmRewardJournalStatus::Missing
                                : ArmRewardJournalStatus::IoError;
    return result;
  }
  const auto count=std::fread(result.bytes.data(),1,result.bytes.size(),f);
  const int trailing=std::fgetc(f);
  const bool read_error=std::ferror(f)!=0;
  const bool closed=std::fclose(f)==0;
  if (read_error || !closed) {
    result.status=ArmRewardJournalStatus::IoError;
    return result;
  }
  if (count!=result.bytes.size() || trailing!=EOF) {
    result.status=ArmRewardJournalStatus::Corrupt;
    return result;
  }
  const auto decoded=decode_arm_reward_record(
      result.bytes.data(),result.bytes.size(),result.generation,result.rewards);
  if (decoded!=ArmRewardRecordStatus::Decoded) {
    result.status=ArmRewardJournalStatus::Corrupt;
    return result;
  }
  result.status=ArmRewardJournalStatus::Loaded;
  return result;
}

[[nodiscard]] inline ArmRewardJournalLoad load_arm_reward_file(
    const std::string& base, BattleRewardAccount& destination) noexcept {
  const auto a=read_arm_reward_journal_slot(base+".a");
  const auto b=read_arm_reward_journal_slot(base+".b");
  if (a.status==ArmRewardJournalStatus::IoError ||
      b.status==ArmRewardJournalStatus::IoError)
    return {ArmRewardJournalStatus::IoError};
  const bool av=a.status==ArmRewardJournalStatus::Loaded;
  const bool bv=b.status==ArmRewardJournalStatus::Loaded;
  if (av && bv && a.generation==b.generation && a.bytes!=b.bytes)
    return {ArmRewardJournalStatus::Corrupt};
  if (!av && !bv) {
    return {a.status==ArmRewardJournalStatus::Missing &&
            b.status==ArmRewardJournalStatus::Missing
              ? ArmRewardJournalStatus::Missing
              : ArmRewardJournalStatus::Corrupt};
  }
  const auto& chosen=!bv || (av && a.generation>=b.generation) ? a : b;
  destination=chosen.rewards;
  return {ArmRewardJournalStatus::Loaded,
          a.status==ArmRewardJournalStatus::Corrupt ||
          b.status==ArmRewardJournalStatus::Corrupt,
          chosen.generation};
}

[[nodiscard]] inline ArmRewardJournalStatus store_arm_reward_file(
    const BattleRewardAccount& rewards, const std::string& base,
    ArmRewardJournalInterruption simulate=ArmRewardJournalInterruption::None)
    noexcept {
  const auto a=read_arm_reward_journal_slot(base+".a");
  const auto b=read_arm_reward_journal_slot(base+".b");
  if (a.status==ArmRewardJournalStatus::IoError ||
      b.status==ArmRewardJournalStatus::IoError)
    return ArmRewardJournalStatus::IoError;
  const bool av=a.status==ArmRewardJournalStatus::Loaded;
  const bool bv=b.status==ArmRewardJournalStatus::Loaded;
  if (av && bv && a.generation==b.generation && a.bytes!=b.bytes)
    return ArmRewardJournalStatus::Corrupt;
  if (!av && !bv &&
      (a.status==ArmRewardJournalStatus::Corrupt ||
       b.status==ArmRewardJournalStatus::Corrupt))
    return ArmRewardJournalStatus::Corrupt;

  const bool latest_a=av && (!bv || a.generation>=b.generation);
  const auto latest=(av || bv)
      ? (latest_a ? a.generation : b.generation) : std::uint64_t{0};
  if (latest==std::numeric_limits<std::uint64_t>::max())
    return ArmRewardJournalStatus::SequenceExhausted;

  const auto generation=latest+1;
  const std::string target=base+(latest_a ? ".b" : ".a");
  const std::string temp=target+".tmp";
  ArmRewardJournalRecord payload{};
  if (encode_arm_reward_record(generation,rewards,payload)!=
      ArmRewardRecordStatus::Encoded)
    return ArmRewardJournalStatus::Corrupt;

  std::FILE* f=std::fopen(temp.c_str(),"wb");
  if (!f) return ArmRewardJournalStatus::IoError;
  if (simulate==ArmRewardJournalInterruption::AfterShortTemporary) {
    (void)std::fwrite(payload.data(),1,11,f);
    (void)std::fclose(f);
    return ArmRewardJournalStatus::IoError;
  }
  const bool complete=
      std::fwrite(payload.data(),1,payload.size(),f)==payload.size() &&
      std::fflush(f)==0 && ::fsync(::fileno(f))==0;
  const bool closed=std::fclose(f)==0;
  if (!complete || !closed) return ArmRewardJournalStatus::IoError;
  if (simulate==ArmRewardJournalInterruption::AfterTemporarySynced)
    return ArmRewardJournalStatus::IoError;

  // Validate the complete temporary record before touching the older slot.
  const auto checked=read_arm_reward_journal_slot(temp);
  if (checked.status!=ArmRewardJournalStatus::Loaded ||
      checked.generation!=generation || checked.bytes!=payload)
    return ArmRewardJournalStatus::IoError;
  if (simulate==ArmRewardJournalInterruption::AfterTemporaryValidated)
    return ArmRewardJournalStatus::IoError;

  // Only the older/invalid slot is replaced; the newest valid slot survives.
  errno=0;
  if (std::remove(target.c_str())!=0 && errno!=ENOENT)
    return ArmRewardJournalStatus::IoError;
  if (simulate==ArmRewardJournalInterruption::AfterTargetRemoved)
    return ArmRewardJournalStatus::IoError;
  if (std::rename(temp.c_str(),target.c_str())!=0)
    return ArmRewardJournalStatus::IoError;
  if (simulate==ArmRewardJournalInterruption::AfterRenamed)
    return ArmRewardJournalStatus::IoError;

  const auto published=read_arm_reward_journal_slot(target);
  if (published.status!=ArmRewardJournalStatus::Loaded ||
      published.generation!=generation || published.bytes!=payload)
    return ArmRewardJournalStatus::IoError;
  // Host fsync/readback tests do not guarantee SD/FAT power-cut durability.
  return ArmRewardJournalStatus::Stored;
}

} // namespace wa::field
