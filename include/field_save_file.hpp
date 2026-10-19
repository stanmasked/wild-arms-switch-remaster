#pragma once

#include "field_save_codec.hpp"

#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <unistd.h>

namespace wa::field {

// Stage 294: two generations, each on its own validated file.
// A complete older slot is never removed during a normal write of a
// replacement into the *other* slot. No game assets are embedded here.
// SD/FAT crash consistency and physical hardware operation are NOT assured.
constexpr std::size_t kFieldJournalBytes = 56;
using FieldJournalBytes = std::array<std::uint8_t, kFieldJournalBytes>;

enum class FileSaveStatus {
  Stored, Loaded, Missing, Corrupt, InvalidWorld, InvalidState,
  IoError, SequenceExhausted
};

// Test-only simulated interruption points. Production calls use the default
// None: no storage hooks, no deliberate errors. These are deterministic
// host-file-system simulations, not a substitute for physical power cuts.
enum class JournalInterruption {
  None,
  AfterShortTemporaryWrite,
  AfterTemporarySynced,
  AfterTemporaryValidated,
  AfterPreviousSlotRemoved,
  AfterNewSlotRenamed,
  // Test-only false negatives, not crashes; verification still proceeds.
  AfterNewSlotRenamedReportedFailure,
  AfterPostPublishFirstReadRejected
};

struct FileSaveSlot {
  FileSaveStatus status = FileSaveStatus::Missing;
  std::uint64_t generation = 0;
  WorldState world{};
  FieldJournalBytes bytes{};
};

[[nodiscard]] inline FileSaveSlot read_field_journal_slot(
    const FieldWorld& world, const std::string& path) noexcept {
  FileSaveSlot slot{};
  errno = 0;
  std::FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) {
    slot.status = errno == ENOENT ? FileSaveStatus::Missing
                                  : FileSaveStatus::IoError;
    return slot;
  }
  const std::size_t count =
      std::fread(slot.bytes.data(), 1, slot.bytes.size(), f);
  const int extra = std::fgetc(f);
  const bool io_error = std::ferror(f) != 0;
  const bool closed = std::fclose(f) == 0;
  if (io_error || !closed) {
    slot.status = FileSaveStatus::IoError;
    return slot;
  }
  if (count != slot.bytes.size() || extra != EOF) {
    slot.status = FileSaveStatus::Corrupt;
    return slot;
  }
  const auto& p = slot.bytes;
  if (p[0] != 'W' || p[1] != 'A' || p[2] != 'J' || p[3] != '1' ||
      save_crc32(p.data(), 52) != save_get_u32(p.data() + 52)) {
    slot.status = FileSaveStatus::Corrupt;
    return slot;
  }
  slot.generation = save_get_u64(p.data() + 4);
  if (slot.generation == 0 ||
      decode_field_save(world, p.data() + 12, kFieldSaveRecordSize,
                        slot.world) != FieldSaveStatus::Decoded) {
    slot.status = FileSaveStatus::Corrupt;
    return slot;
  }
  slot.status = FileSaveStatus::Loaded;
  return slot;
}

// A readable slot plus a damaged peer is still a successful load, but its
// redundancy is compromised. Preserve the original FileSaveStatus ABI and
// expose a separate diagnostic for the frontend; never replace the world
// unless a complete validated journal is available.
struct FileSaveLoadResult {
  FileSaveStatus status = FileSaveStatus::Missing;
  bool degraded = false;  // Another committed slot was unreadable/corrupt.
  std::uint64_t selected_generation = 0;
};

// Valid newer generations take precedence. A damaged peer can be bypassed,
// but never interpreted as a valid save or used to modify the destination.
[[nodiscard]] inline FileSaveLoadResult load_field_save_file_detailed(
    const FieldWorld& world, const std::string& base_path,
    WorldState& destination) noexcept {
  if (!world.valid()) return {FileSaveStatus::InvalidWorld};
  const FileSaveSlot a = read_field_journal_slot(world, base_path + ".a");
  const FileSaveSlot b = read_field_journal_slot(world, base_path + ".b");
  if (a.status == FileSaveStatus::IoError ||
      b.status == FileSaveStatus::IoError)
    return {FileSaveStatus::IoError};
  const bool av = a.status == FileSaveStatus::Loaded;
  const bool bv = b.status == FileSaveStatus::Loaded;
  if (av && bv && a.generation == b.generation &&
      a.bytes != b.bytes)
    return {FileSaveStatus::Corrupt};
  if (av || bv) {
    const FileSaveSlot& selected =
        (!bv || (av && a.generation >= b.generation)) ? a : b;
    destination = selected.world;
    return {FileSaveStatus::Loaded,
            a.status == FileSaveStatus::Corrupt ||
            b.status == FileSaveStatus::Corrupt,
            selected.generation};
  }
  return {(a.status == FileSaveStatus::Missing &&
           b.status == FileSaveStatus::Missing)
              ? FileSaveStatus::Missing : FileSaveStatus::Corrupt};
}

[[nodiscard]] inline FileSaveStatus load_field_save_file(
    const FieldWorld& world, const std::string& base_path,
    WorldState& destination) noexcept {
  return load_field_save_file_detailed(world, base_path, destination).status;
}

[[nodiscard]] inline FileSaveStatus store_field_save_file(
    const FieldWorld& world, const WorldState& state,
    const std::string& base_path,
    JournalInterruption simulate = JournalInterruption::None) noexcept {
  if (!world.valid()) return FileSaveStatus::InvalidWorld;
  FieldSaveRecord encoded{};
  if (encode_field_save(world, state, encoded) != FieldSaveStatus::Encoded)
    return FileSaveStatus::InvalidState;

  const FileSaveSlot a = read_field_journal_slot(world, base_path + ".a");
  const FileSaveSlot b = read_field_journal_slot(world, base_path + ".b");
  if (a.status == FileSaveStatus::IoError ||
      b.status == FileSaveStatus::IoError)
    return FileSaveStatus::IoError;
  const bool av = a.status == FileSaveStatus::Loaded;
  const bool bv = b.status == FileSaveStatus::Loaded;
  if (av && bv && a.generation == b.generation &&
      a.bytes != b.bytes)
    return FileSaveStatus::Corrupt;
  const bool latest_is_a = av && (!bv || a.generation >= b.generation);
  const std::uint64_t latest =
      av || bv ? (latest_is_a ? a.generation : b.generation) : 0;
  if (latest == std::numeric_limits<std::uint64_t>::max())
    return FileSaveStatus::SequenceExhausted;

  // If the most recent valid generation is A, target B; otherwise target A.
  // The latest verified slot is not unlinked or overwritten.
  const std::string target = base_path + (latest_is_a ? ".b" : ".a");
  const std::string temporary = target + ".tmp";
  FieldJournalBytes payload{};
  payload[0] = 'W'; payload[1] = 'A'; payload[2] = 'J'; payload[3] = '1';
  save_put_u64(payload.data() + 4, latest + 1);
  for (std::size_t i = 0; i < encoded.size(); ++i)
    payload[12 + i] = encoded[i];
  save_put_u32(payload.data() + 52, save_crc32(payload.data(), 52));

  // The temporary file is never considered a committed save at load time.
  std::FILE* f = std::fopen(temporary.c_str(), "wb");
  if (!f) return FileSaveStatus::IoError;
  if (simulate == JournalInterruption::AfterShortTemporaryWrite) {
    // A process stop while writing the 56 bytes: a deliberately incomplete
    // .tmp is left. Neither .a nor .b is touched; readers never load .tmp.
    (void)std::fwrite(payload.data(), 1, 11, f);
    (void)std::fclose(f);
    return FileSaveStatus::IoError;
  }
  const bool complete =
      std::fwrite(payload.data(), 1, payload.size(), f) == payload.size() &&
      std::fflush(f) == 0 && ::fsync(::fileno(f)) == 0;
  const bool closed = std::fclose(f) == 0;
  if (!complete || !closed) {
    (void)std::remove(temporary.c_str());
    return FileSaveStatus::IoError;
  }
  if (simulate == JournalInterruption::AfterTemporarySynced)
    return FileSaveStatus::IoError;  // Complete uncommitted .tmp survives.

  // Re-open and validate from storage before making the new file visible.
  const FileSaveSlot verified = read_field_journal_slot(world, temporary);
  if (verified.status != FileSaveStatus::Loaded ||
      verified.bytes != payload) {
    (void)std::remove(temporary.c_str());
    return FileSaveStatus::IoError;
  }
  if (simulate == JournalInterruption::AfterTemporaryValidated)
    return FileSaveStatus::IoError;

  // libnx's sdmc rename does not promise POSIX overwrite. Only the *older*
  // slot can be deleted; the newest valid generation survives any failure.
  errno = 0;
  if (std::remove(target.c_str()) != 0 && errno != ENOENT) {
    (void)std::remove(temporary.c_str());
    return FileSaveStatus::IoError;
  }
  if (simulate == JournalInterruption::AfterPreviousSlotRemoved)
    return FileSaveStatus::IoError;
  // NeXium's emulated filesystem can return a false-negative publishing
  // status after a complete record has become visible. Only the actual
  // *fully validated record*, never the API return code alone, proves
  // durability at this emulated-filesystem level.
  const bool renamed = std::rename(temporary.c_str(), target.c_str()) == 0;
  const bool rename_reported_success =
      renamed &&
      simulate != JournalInterruption::AfterNewSlotRenamedReportedFailure;
  if (simulate == JournalInterruption::AfterNewSlotRenamed && renamed)
    return FileSaveStatus::IoError;  // Simulated interrupted process.

  // Try a bounded number of separately opened full record reads. The
  // payload comparison includes journal generation, encoded world and CRC.
  constexpr int kPostPublishReadAttempts = 3;
  for (int attempt = 0; attempt < kPostPublishReadAttempts; ++attempt) {
    FileSaveSlot published{};
    if (simulate == JournalInterruption::AfterPostPublishFirstReadRejected &&
        attempt == 0) {
      published.status = FileSaveStatus::IoError;  // Test-only false read.
    } else {
      published = read_field_journal_slot(world, target);
    }
    if (published.status == FileSaveStatus::Loaded &&
        published.bytes == payload) {
      // A non-successful rename report cannot override exact committed
      // content. If the move actually failed, discard any leftover .tmp.
      if (!rename_reported_success)
        (void)std::remove(temporary.c_str());
      return FileSaveStatus::Stored;
    }
  }
  // If no read proved the expected committed record, fail closed.
  (void)std::remove(temporary.c_str());
  return FileSaveStatus::IoError;
}

}  // namespace wa::field
