#pragma once
// Stage 358: independent, ROM-free in-memory battle-progress save codec.
// This is NOT a file writer; no automatic SD operations or field save edits.
#include "field_battle_rewards.hpp"
#include "field_save_codec.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {

constexpr std::size_t kBattleRecordBytes = 36;
constexpr std::uint8_t kBattleRecordVersion = 1;
using BattleRecord = std::array<std::uint8_t, kBattleRecordBytes>;

struct BattleProgress {
  BattleHistory history{};
  BattleRewardAccount rewards{};
};

enum class BattleRecordStatus : std::uint8_t {
  Encoded, Decoded, InvalidValues, InvalidLength,
  InvalidMagic, UnsupportedVersion, InvalidChecksum, Malformed
};

[[nodiscard]] constexpr bool battle_progress_valid(
    const BattleProgress& data) noexcept {
  const auto& h=data.history;
  switch (h.last) {
    case BattleResolution::None:
      if (h.victories || h.defeats || h.retreats) return false;
      break;
    case BattleResolution::Victory:
      if (!h.victories) return false;
      break;
    case BattleResolution::Defeat:
      if (!h.defeats) return false;
      break;
    case BattleResolution::Retreat:
      if (!h.retreats) return false;
      break;
    default: return false;
  }
  // The experimental economy earns currency only from a completed win.
  if (!h.victories && (data.rewards.experience || data.rewards.gella))
    return false;
  return true;
}

// Exact v1 little-endian binary layout, independent of C++ struct padding:
// 0..3 'WABR'; 4 version=1; 5 last outcome;
// 6..7 reserved 0; 8..11 wins; 12..15 defeats; 16..19 retreats;
// 20..23 EXP; 24..27 Gella; 28..31 reserved 0;
// 32..35 CRC32 on bytes 0..31.
// CRC32 detects accidental corruption but is not cryptographic security.
[[nodiscard]] inline BattleRecordStatus encode_battle_progress(
    const BattleProgress& data, BattleRecord& out) noexcept {
  if (!battle_progress_valid(data)) return BattleRecordStatus::InvalidValues;
  BattleRecord next{};
  next[0]='W';next[1]='A';next[2]='B';next[3]='R';
  next[4]=kBattleRecordVersion;
  next[5]=static_cast<std::uint8_t>(data.history.last);
  save_put_u32(next.data()+8,data.history.victories);
  save_put_u32(next.data()+12,data.history.defeats);
  save_put_u32(next.data()+16,data.history.retreats);
  save_put_u32(next.data()+20,data.rewards.experience);
  save_put_u32(next.data()+24,data.rewards.gella);
  save_put_u32(next.data()+32,save_crc32(next.data(),32));
  out=next;
  return BattleRecordStatus::Encoded;
}

// Decode atomically: malformed/corrupt bytes never mutate the supplied
// current battle progress. Exact size and reserved bytes required.
[[nodiscard]] inline BattleRecordStatus decode_battle_progress(
    const std::uint8_t* data, std::size_t size,
    BattleProgress& in_out) noexcept {
  if (!data || size!=kBattleRecordBytes)
    return BattleRecordStatus::InvalidLength;
  if (data[0]!='W'||data[1]!='A'||data[2]!='B'||data[3]!='R')
    return BattleRecordStatus::InvalidMagic;
  if (data[4]!=kBattleRecordVersion)
    return BattleRecordStatus::UnsupportedVersion;
  for (std::size_t i=6;i<8;++i)
    if (data[i]!=0) return BattleRecordStatus::Malformed;
  for (std::size_t i=28;i<32;++i)
    if (data[i]!=0) return BattleRecordStatus::Malformed;
  if (save_crc32(data,32)!=save_get_u32(data+32))
    return BattleRecordStatus::InvalidChecksum;

  BattleProgress next{};
  next.history.last=static_cast<BattleResolution>(data[5]);
  next.history.victories=save_get_u32(data+8);
  next.history.defeats=save_get_u32(data+12);
  next.history.retreats=save_get_u32(data+16);
  next.rewards.experience=save_get_u32(data+20);
  next.rewards.gella=save_get_u32(data+24);
  if (!battle_progress_valid(next))
    return BattleRecordStatus::InvalidValues;
  in_out=next;
  return BattleRecordStatus::Decoded;
}

}  // namespace wa::field
