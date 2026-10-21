#include "field_save_codec.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <limits>

namespace {
using namespace wa::field;
void require(bool ok) { if (!ok) std::abort(); }

void same(const WorldState& a, const WorldState& b) {
  require(a.area == b.area && a.player.x == b.player.x &&
          a.player.y == b.player.y &&
          a.player.facing == b.player.facing &&
          a.player.successful_moves == b.player.successful_moves &&
          a.pending == b.pending &&
          a.clock.cadence_ms == b.clock.cadence_ms &&
          a.clock.carry_ms == b.clock.carry_ms &&
          a.clock.held == b.clock.held &&
          a.clock.paused_for_trigger == b.clock.paused_for_trigger &&
          a.decoder.confirm_down == b.decoder.confirm_down);
}

void resign(FieldSaveRecord& record) {
  save_put_u32(record.data() + 36, save_crc32(record.data(), 36));
}

void test_golden_encoding_and_round_trip() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  state.player.successful_moves = UINT64_C(0x0123456789ABCDEF);
  state.clock.cadence_ms = 160;
  state.clock.carry_ms = 12;
  state.clock.held = Direction::Right;
  state.decoder.confirm_down = true;

  FieldSaveRecord encoded{};
  require(encode_field_save(world, state, encoded) == FieldSaveStatus::Encoded);
  require(encoded.size() == 40 && encoded[0] == 'W' &&
          encoded[1] == 'A' && encoded[2] == 'F' && encoded[3] == 'S');
  require(encoded[4] == 1 && encoded[14] == 160 && encoded[15] == 0);
  require(encoded[18] == 0xEF && encoded[19] == 0xCD &&
          encoded[24] == 0x23 && encoded[25] == 0x01);
  require(encoded[13] == 0 && encoded[34] == 0 && encoded[35] == 0);
  require(save_get_u32(encoded.data() + 36) ==
          save_crc32(encoded.data(), 36));

  WorldState decoded{};
  require(decode_field_save(world, encoded, decoded) ==
          FieldSaveStatus::Decoded);
  same(state, decoded);
  FieldSaveRecord replay{};
  require(encode_field_save(world, decoded, replay) ==
          FieldSaveStatus::Encoded);
  require(replay == encoded);

  const WorldState old = decoded;
  require(decode_field_save(world, encoded.data(), 39, decoded) ==
          FieldSaveStatus::InvalidLength);
  same(old, decoded);
  require(decode_field_save(world, encoded.data(), 41, decoded) ==
          FieldSaveStatus::InvalidLength);
  same(old, decoded);
  require(decode_field_save(world, nullptr, 40, decoded) ==
          FieldSaveStatus::InvalidLength);
}

void test_event_pause_restored_with_decoder_edge() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  for (int i = 0; i < 3; ++i) {
    auto result = advance_world_frame(
        world, state, PadSample{.dpad_right = true}, 160);
    require(result.controller.movement.successful_steps == 1);
  }
  require(state.pending == Trigger::Event &&
          state.clock.paused_for_trigger);
  FieldSaveRecord saved{};
  require(encode_field_save(world,state,saved) == FieldSaveStatus::Encoded);
  WorldState recovered = start_world(world);
  require(decode_field_save(world,saved,recovered) == FieldSaveStatus::Decoded);
  same(state,recovered);
  const auto ack = PadSample{.confirm = true};
  const auto a = advance_world_frame(world,state,ack,160);
  const auto b = advance_world_frame(world,recovered,ack,160);
  require(a.controller.outcome == PadFrameOutcome::Acknowledged &&
          b.controller.outcome == PadFrameOutcome::Acknowledged);
  same(state,recovered);
  require(!recovered.clock.paused_for_trigger &&
          recovered.pending == Trigger::None);
}

void test_corruption_rejections_are_transactional() {
  FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  WorldState destination = state;
  destination.player.successful_moves = 77;
  const WorldState original = destination;
  FieldSaveRecord record{};
  require(encode_field_save(world,state,record) == FieldSaveStatus::Encoded);
  FieldSaveRecord bad = record;
  bad[0] = 'X';
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::InvalidMagic);
  same(original,destination);
  bad = record;
  bad[4] = 2;
  resign(bad);
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::UnsupportedVersion);
  bad = record;
  bad[18] ^= 1;
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::InvalidChecksum);
  bad = record;
  bad[8] = 255;
  resign(bad);
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::Malformed);
  bad = record;
  bad[34] = 1;
  resign(bad);
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::Malformed);
  bad = record;
  bad[5] = 2;
  resign(bad);
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::InvalidState);
  bad = record;
  bad[9] = 2; // claim pending Exit at start floor
  bad[11] = 1;
  resign(bad);
  require(decode_field_save(world,bad,destination) ==
          FieldSaveStatus::InvalidState);
  same(original,destination);

  FieldWorld changed = make_demo_world();
  changed.areas[1].map.tiles[13] = '#'; // nonentrance, valid map edit
  require(changed.valid());
  require(decode_field_save(changed,record,destination) ==
          FieldSaveStatus::WorldMismatch);
  same(original,destination);
  changed = make_demo_world();
  changed.areas[0].entrance_x = 0;
  require(decode_field_save(changed,record,destination) ==
          FieldSaveStatus::InvalidWorld);
}

void test_failed_encode_does_not_overwrite_record() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  FieldSaveRecord out{};
  out.fill(0xA5);
  FieldSaveRecord before = out;
  state.player.x = -1;
  require(encode_field_save(world,state,out) ==
          FieldSaveStatus::InvalidState);
  require(out == before);
  FieldWorld broken = world;
  broken.areas[0].entrance_x = 0;
  require(encode_field_save(broken,start_world(world),out) ==
          FieldSaveStatus::InvalidWorld);
  require(out == before);
}

void test_canonical_record_preserves_maximum_moves() {
  const FieldWorld world = make_demo_world();
  WorldState state = start_world(world);
  state.player.successful_moves =
      std::numeric_limits<std::uint64_t>::max();
  FieldSaveRecord data{};
  require(encode_field_save(world,state,data) == FieldSaveStatus::Encoded);
  WorldState recovered{};
  require(decode_field_save(world,data,recovered) ==
          FieldSaveStatus::Decoded);
  same(state,recovered);
}
}

int main() {
  test_golden_encoding_and_round_trip();
  test_event_pause_restored_with_decoder_edge();
  test_corruption_rejections_are_transactional();
  test_failed_encode_does_not_overwrite_record();
  test_canonical_record_preserves_maximum_moves();
}
