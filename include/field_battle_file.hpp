#pragma once
// Stage 359: independent two-slot battle-progress journal.
// Never modify the 40-byte WAFS field save or field-save.a/.b.
#include "field_battle_record.hpp"

#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <unistd.h>

namespace wa::field {

constexpr std::size_t kBattleJournalBytes = 52;
using BattleJournalRecord = std::array<std::uint8_t, kBattleJournalBytes>;

enum class BattleJournalStatus : std::uint8_t {
  Stored, Loaded, Missing, Corrupt, InvalidProgress,
  IoError, SequenceExhausted
};

enum class BattleJournalInterruption : std::uint8_t {
  None, AfterShortTemporary, AfterTemporarySynced,
  AfterTargetRemoved, AfterRenamed
};

struct BattleJournalSlot {
  BattleJournalStatus status = BattleJournalStatus::Missing;
  std::uint64_t generation = 0;
  BattleProgress progress{};
  BattleJournalRecord raw{};
};
struct BattleJournalLoad {
  BattleJournalStatus status = BattleJournalStatus::Missing;
  bool degraded = false;
  std::uint64_t generation = 0;
};

// WABJ + u64 LE generation + WABR[36] + CRC32 on 48 bytes.
[[nodiscard]] inline BattleJournalSlot read_battle_journal_slot(
    const std::string& path) noexcept {
  BattleJournalSlot result{};
  errno = 0;
  std::FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) {
    result.status = errno == ENOENT ? BattleJournalStatus::Missing
                                    : BattleJournalStatus::IoError;
    return result;
  }
  const std::size_t count =
      std::fread(result.raw.data(), 1, result.raw.size(), f);
  const int trailing = std::fgetc(f);
  const bool read_error = std::ferror(f) != 0;
  const bool end_of_file = std::feof(f) != 0;
  const bool closed = std::fclose(f) == 0;
  if (read_error || !closed) {
    result.status = BattleJournalStatus::IoError;
    return result;
  }
  if (count != result.raw.size() || trailing != EOF || !end_of_file) {
    result.status = BattleJournalStatus::Corrupt;
    return result;
  }
  const auto* p = result.raw.data();
  if (p[0]!='W' || p[1]!='A' || p[2]!='B' || p[3]!='J' ||
      save_crc32(p, 48) != save_get_u32(p + 48)) {
    result.status = BattleJournalStatus::Corrupt;
    return result;
  }
  result.generation = save_get_u64(p + 4);
  if (result.generation == 0 ||
      decode_battle_progress(p + 12, kBattleRecordBytes,
                             result.progress) != BattleRecordStatus::Decoded) {
    result.status = BattleJournalStatus::Corrupt;
    return result;
  }
  result.status = BattleJournalStatus::Loaded;
  return result;
}

// Reader ignores .tmp entirely; a complete .a or .b is the only commit.
// Returns the last fully validated generation, never a partial payload.
[[nodiscard]] inline BattleJournalLoad load_battle_progress_file(
    const std::string& base, BattleProgress& destination) noexcept {
  const BattleJournalSlot a = read_battle_journal_slot(base + ".a");
  const BattleJournalSlot b = read_battle_journal_slot(base + ".b");
  if (a.status == BattleJournalStatus::IoError ||
      b.status == BattleJournalStatus::IoError)
    return {BattleJournalStatus::IoError};
  const bool av = a.status == BattleJournalStatus::Loaded;
  const bool bv = b.status == BattleJournalStatus::Loaded;
  if (av && bv && a.generation == b.generation && a.raw != b.raw)
    return {BattleJournalStatus::Corrupt};
  if (!av && !bv) {
    return {a.status == BattleJournalStatus::Missing &&
                    b.status == BattleJournalStatus::Missing
                ? BattleJournalStatus::Missing : BattleJournalStatus::Corrupt};
  }
  const BattleJournalSlot& chosen =
      !bv || (av && a.generation >= b.generation) ? a : b;
  destination = chosen.progress;
  return {BattleJournalStatus::Loaded,
          a.status == BattleJournalStatus::Corrupt ||
          b.status == BattleJournalStatus::Corrupt,
          chosen.generation};
}

[[nodiscard]] inline BattleJournalStatus store_battle_progress_file(
    const BattleProgress& value, const std::string& base,
    BattleJournalInterruption simulate = BattleJournalInterruption::None) noexcept {
  BattleRecord encoded{};
  if (encode_battle_progress(value, encoded) != BattleRecordStatus::Encoded)
    return BattleJournalStatus::InvalidProgress;

  const BattleJournalSlot a = read_battle_journal_slot(base + ".a");
  const BattleJournalSlot b = read_battle_journal_slot(base + ".b");
  if (a.status == BattleJournalStatus::IoError ||
      b.status == BattleJournalStatus::IoError)
    return BattleJournalStatus::IoError;
  const bool av = a.status == BattleJournalStatus::Loaded;
  const bool bv = b.status == BattleJournalStatus::Loaded;
  if (av && bv && a.generation == b.generation && a.raw != b.raw)
    return BattleJournalStatus::Corrupt;
  if (!av && !bv &&
      (a.status == BattleJournalStatus::Corrupt ||
       b.status == BattleJournalStatus::Corrupt))
    return BattleJournalStatus::Corrupt;
  const bool latest_a = av && (!bv || a.generation >= b.generation);
  const auto latest = (av || bv)
      ? (latest_a ? a.generation : b.generation) : std::uint64_t{0};
  if (latest == std::numeric_limits<std::uint64_t>::max())
    return BattleJournalStatus::SequenceExhausted;

  const std::string target = base + (latest_a ? ".b" : ".a");
  const std::string temp = target + ".tmp";
  BattleJournalRecord payload{};
  payload[0]='W';payload[1]='A';payload[2]='B';payload[3]='J';
  save_put_u64(payload.data()+4, latest+1);
  for(std::size_t i=0;i<encoded.size();++i) payload[i+12]=encoded[i];
  save_put_u32(payload.data()+48,save_crc32(payload.data(),48));

  std::FILE* f = std::fopen(temp.c_str(), "wb");
  if (!f) return BattleJournalStatus::IoError;
  if (simulate == BattleJournalInterruption::AfterShortTemporary) {
    (void)std::fwrite(payload.data(),1,11,f);
    (void)std::fclose(f);
    return BattleJournalStatus::IoError;
  }
  const bool complete =
      std::fwrite(payload.data(),1,payload.size(),f)==payload.size() &&
      std::fflush(f)==0 && ::fsync(::fileno(f))==0;
  const bool closed = std::fclose(f)==0;
  if (!complete || !closed) return BattleJournalStatus::IoError;
  if (simulate == BattleJournalInterruption::AfterTemporarySynced)
    return BattleJournalStatus::IoError;

  // Read back the durable temporary file and validate every byte BEFORE
  // touching any committed slot. Never overwrite the newest valid copy.
  const auto checked = read_battle_journal_slot(temp);
  if (checked.status != BattleJournalStatus::Loaded ||
      checked.generation != latest+1 || checked.raw != payload)
    return BattleJournalStatus::IoError;

  // libnx SDMC rename does not guarantee replacing an existing target.
  // Only remove the older slot (or a corrupt/non-existent slot).
  errno = 0;
  if (std::remove(target.c_str()) != 0 && errno != ENOENT)
    return BattleJournalStatus::IoError;
  if (simulate == BattleJournalInterruption::AfterTargetRemoved)
    return BattleJournalStatus::IoError;
  if (std::rename(temp.c_str(),target.c_str()) != 0)
    return BattleJournalStatus::IoError;
  if (simulate == BattleJournalInterruption::AfterRenamed)
    return BattleJournalStatus::IoError;

  const auto published = read_battle_journal_slot(target);
  if (published.status != BattleJournalStatus::Loaded ||
      published.generation != latest+1 || published.raw != payload)
    return BattleJournalStatus::IoError;
  // File fsync+rename is best-effort on SD/FAT; this does not certify
  // physical power-cut durability or directory entry fsync on hardware.
  return BattleJournalStatus::Stored;
}

} // namespace wa::field
