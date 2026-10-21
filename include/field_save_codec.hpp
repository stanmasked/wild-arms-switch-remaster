#pragma once

#include "field_snapshot.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::field {

// Stage 293: portable *in-memory byte codec*, not an SD-card save routine.
// Versioned, fixed-size little-endian format with map identity and CRC32.
// Never write a C++ struct's padding or machine-native layout to disk.
constexpr std::size_t kFieldSaveRecordSize = 40;
using FieldSaveRecord = std::array<std::uint8_t, kFieldSaveRecordSize>;
constexpr std::uint8_t kFieldSaveVersion = 1;

enum class FieldSaveStatus {
  Encoded,
  Decoded,
  InvalidWorld,
  InvalidState,
  InvalidLength,
  InvalidMagic,
  UnsupportedVersion,
  InvalidChecksum,
  WorldMismatch,
  Malformed
};

[[nodiscard]] constexpr std::uint16_t save_get_u16(
    const std::uint8_t* p) noexcept {
  return static_cast<std::uint16_t>(
      static_cast<std::uint16_t>(p[0]) |
      (static_cast<std::uint16_t>(p[1]) << 8));
}
[[nodiscard]] constexpr std::uint32_t save_get_u32(
    const std::uint8_t* p) noexcept {
  std::uint32_t value = 0;
  for (int i = 0; i < 4; ++i)
    value |= static_cast<std::uint32_t>(p[i]) << (i * 8);
  return value;
}
[[nodiscard]] constexpr std::uint64_t save_get_u64(
    const std::uint8_t* p) noexcept {
  std::uint64_t value = 0;
  for (int i = 0; i < 8; ++i)
    value |= static_cast<std::uint64_t>(p[i]) << (i * 8);
  return value;
}
constexpr void save_put_u16(std::uint8_t* p, std::uint16_t value) noexcept {
  for (int i = 0; i < 2; ++i)
    p[i] = static_cast<std::uint8_t>(value >> (i * 8));
}
constexpr void save_put_u32(std::uint8_t* p, std::uint32_t value) noexcept {
  for (int i = 0; i < 4; ++i)
    p[i] = static_cast<std::uint8_t>(value >> (i * 8));
}
constexpr void save_put_u64(std::uint8_t* p, std::uint64_t value) noexcept {
  for (int i = 0; i < 8; ++i)
    p[i] = static_cast<std::uint8_t>(value >> (i * 8));
}

[[nodiscard]] inline std::uint32_t save_crc32(
    const std::uint8_t* data, std::size_t count) noexcept {
  std::uint32_t crc = 0xFFFFFFFFu;
  for (std::size_t i = 0; i < count; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ ((crc & 1u) ? 0xEDB88320u : 0u);
  }
  return crc ^ 0xFFFFFFFFu;
}

[[nodiscard]] inline std::uint64_t save_world_fingerprint(
    const FieldWorld& world) noexcept {
  std::uint64_t hash = UINT64_C(14695981039346656037);
  const auto mix = [&hash](std::uint8_t b) {
    hash ^= b;
    hash *= UINT64_C(1099511628211);
  };
  mix(static_cast<std::uint8_t>(kFieldAreaCount));
  for (const FieldArea& area : world.areas) {
    mix(static_cast<std::uint8_t>(area.map.width));
    mix(static_cast<std::uint8_t>(area.map.height));
    mix(static_cast<std::uint8_t>(area.entrance_x));
    mix(static_cast<std::uint8_t>(area.entrance_y));
    for (char tile : area.map.tiles)
      mix(static_cast<std::uint8_t>(static_cast<unsigned char>(tile)));
  }
  return hash;
}

// Exact v1 record layout, all offsets inclusive:
//  0..3 'WAFS', 4 version, 5 area, 6 x, 7 y, 8 facing, 9 pending,
//  10 held, 11 paused, 12 confirm_down, 13 reserved (zero),
//  14..15 movement cadence, 16..17 carry, 18..25 successful moves,
//  26..33 world fingerprint, 34..35 reserved (zero),
//  36..39 CRC32 over bytes 0..35.
// The digest and CRC are non-cryptographic corruption guards, not security
// against maliciously constructed files; no original game data is stored.
[[nodiscard]] inline FieldSaveStatus encode_field_save(
    const FieldWorld& world, const WorldState& state,
    FieldSaveRecord& output) noexcept {
  if (!world.valid()) return FieldSaveStatus::InvalidWorld;
  if (!valid_field_snapshot(world, state))
    return FieldSaveStatus::InvalidState;
  FieldSaveRecord result{};
  result[0] = 'W'; result[1] = 'A'; result[2] = 'F'; result[3] = 'S';
  result[4] = kFieldSaveVersion;
  result[5] = static_cast<std::uint8_t>(state.area);
  result[6] = static_cast<std::uint8_t>(state.player.x);
  result[7] = static_cast<std::uint8_t>(state.player.y);
  result[8] = static_cast<std::uint8_t>(state.player.facing);
  result[9] = static_cast<std::uint8_t>(state.pending);
  result[10] = static_cast<std::uint8_t>(state.clock.held);
  result[11] = static_cast<std::uint8_t>(state.clock.paused_for_trigger);
  result[12] = static_cast<std::uint8_t>(state.decoder.confirm_down);
  save_put_u16(result.data() + 14,
               static_cast<std::uint16_t>(state.clock.cadence_ms));
  save_put_u16(result.data() + 16,
               static_cast<std::uint16_t>(state.clock.carry_ms));
  save_put_u64(result.data() + 18, state.player.successful_moves);
  save_put_u64(result.data() + 26, save_world_fingerprint(world));
  save_put_u32(result.data() + 36, save_crc32(result.data(), 36));
  output = result;
  return FieldSaveStatus::Encoded;
}

// Exact length required; reject invalid bytes *before* touching live state.
[[nodiscard]] inline FieldSaveStatus decode_field_save(
    const FieldWorld& world, const std::uint8_t* bytes,
    std::size_t size, WorldState& state) noexcept {
  if (!world.valid()) return FieldSaveStatus::InvalidWorld;
  if (bytes == nullptr || size != kFieldSaveRecordSize)
    return FieldSaveStatus::InvalidLength;
  if (bytes[0] != 'W' || bytes[1] != 'A' ||
      bytes[2] != 'F' || bytes[3] != 'S')
    return FieldSaveStatus::InvalidMagic;
  if (bytes[4] != kFieldSaveVersion)
    return FieldSaveStatus::UnsupportedVersion;
  if (save_crc32(bytes, 36) != save_get_u32(bytes + 36))
    return FieldSaveStatus::InvalidChecksum;
  if (bytes[13] != 0 || bytes[34] != 0 || bytes[35] != 0 ||
      bytes[8] > 4 || bytes[9] > 2 || bytes[10] > 4 ||
      bytes[11] > 1 || bytes[12] > 1)
    return FieldSaveStatus::Malformed;
  if (save_get_u64(bytes + 26) != save_world_fingerprint(world))
    return FieldSaveStatus::WorldMismatch;

  WorldState candidate{};
  candidate.area = bytes[5];
  candidate.player.x = bytes[6];
  candidate.player.y = bytes[7];
  candidate.player.facing = static_cast<Direction>(bytes[8]);
  candidate.pending = static_cast<Trigger>(bytes[9]);
  candidate.clock.held = static_cast<Direction>(bytes[10]);
  candidate.clock.paused_for_trigger = bytes[11] != 0;
  candidate.decoder.confirm_down = bytes[12] != 0;
  candidate.clock.cadence_ms = save_get_u16(bytes + 14);
  candidate.clock.carry_ms = save_get_u16(bytes + 16);
  candidate.player.successful_moves = save_get_u64(bytes + 18);
  if (!valid_field_snapshot(world, candidate))
    return FieldSaveStatus::InvalidState;

  state = candidate;
  return FieldSaveStatus::Decoded;
}

[[nodiscard]] inline FieldSaveStatus decode_field_save(
    const FieldWorld& world, const FieldSaveRecord& record,
    WorldState& state) noexcept {
  return decode_field_save(world, record.data(), record.size(), state);
}

}  // namespace wa::field
