// Stage 358: strict binary replay boundary, no SD writes.
#include "field_battle_record.hpp"
#include "field_battle_session.hpp"

#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

using namespace wa::field;
namespace {
BattleProgress example(){
  BattleProgress p{};
  p.history.victories=2;
  p.history.defeats=1;
  p.history.retreats=3;
  p.history.last=BattleResolution::Retreat;
  p.rewards.experience=16;
  p.rewards.gella=24;
  return p;
}
void match(const BattleProgress& p,const BattleProgress& q){
  assert(p.history.victories==q.history.victories);
  assert(p.history.defeats==q.history.defeats);
  assert(p.history.retreats==q.history.retreats);
  assert(p.history.last==q.history.last);
  assert(p.rewards.experience==q.rewards.experience);
  assert(p.rewards.gella==q.rewards.gella);
}
void test_empty_and_real_record_roundtrip(){
  BattleProgress empty{};
  BattleRecord bytes{};
  assert(encode_battle_progress(empty,bytes)==BattleRecordStatus::Encoded);
  assert(bytes[0]=='W'&&bytes[1]=='A'&&bytes[2]=='B'&&bytes[3]=='R');
  assert(bytes[4]==1&&bytes[5]==0);
  assert(save_get_u32(bytes.data()+32)==save_crc32(bytes.data(),32));
  BattleProgress recovered=example();
  assert(decode_battle_progress(bytes.data(),bytes.size(),recovered)==
         BattleRecordStatus::Decoded);
  match(empty,recovered);
  const auto original=example();
  assert(encode_battle_progress(original,bytes)==BattleRecordStatus::Encoded);
  assert(save_get_u32(bytes.data()+8)==2);
  assert(save_get_u32(bytes.data()+12)==1);
  assert(save_get_u32(bytes.data()+16)==3);
  assert(save_get_u32(bytes.data()+20)==16);
  assert(save_get_u32(bytes.data()+24)==24);
  recovered={};
  assert(decode_battle_progress(bytes.data(),bytes.size(),recovered)==
         BattleRecordStatus::Decoded);
  match(original,recovered);
}
void test_reject_invalid_lengths_magic_version_checksum_atomic(){
  auto initial=example();
  BattleRecord bytes{};
  assert(encode_battle_progress(initial,bytes)==BattleRecordStatus::Encoded);
  const auto original=bytes;
  BattleProgress live=initial;
  assert(decode_battle_progress(nullptr,36,live)==
         BattleRecordStatus::InvalidLength);
  assert(decode_battle_progress(bytes.data(),35,live)==
         BattleRecordStatus::InvalidLength);
  std::array<std::uint8_t,kBattleRecordBytes+1> extra{};
  for(std::size_t i=0;i<bytes.size();++i)extra[i]=bytes[i];
  assert(decode_battle_progress(extra.data(),extra.size(),live)==
         BattleRecordStatus::InvalidLength);
  match(live,initial);

  bytes[2]='X';
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::InvalidMagic);
  bytes=original;
  bytes[4]=2;
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::UnsupportedVersion);
  bytes=original;
  bytes[12]^=0x80; // Corrupt one defeated-count byte.
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::InvalidChecksum);
  match(live,initial);
}
void test_reserved_and_malformed_values_rejected_even_with_correct_crc(){
  const auto initial=example();
  BattleRecord bytes{};
  assert(encode_battle_progress(initial,bytes)==BattleRecordStatus::Encoded);
  BattleProgress live=initial;
  bytes[7]=1;
  save_put_u32(bytes.data()+32,save_crc32(bytes.data(),32));
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::Malformed);
  assert(encode_battle_progress(initial,bytes)==BattleRecordStatus::Encoded);
  bytes[29]=1;
  save_put_u32(bytes.data()+32,save_crc32(bytes.data(),32));
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::Malformed);

  assert(encode_battle_progress(initial,bytes)==BattleRecordStatus::Encoded);
  bytes[5]=99;
  save_put_u32(bytes.data()+32,save_crc32(bytes.data(),32));
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::InvalidValues);

  assert(encode_battle_progress(initial,bytes)==BattleRecordStatus::Encoded);
  save_put_u32(bytes.data()+8,0);
  save_put_u32(bytes.data()+20,8);
  save_put_u32(bytes.data()+32,save_crc32(bytes.data(),32));
  assert(decode_battle_progress(bytes.data(),bytes.size(),live)==
         BattleRecordStatus::InvalidValues);
  match(live,initial);
}
void test_invalid_encoding_cannot_modify_output(){
  auto invalid=example();
  invalid.history.last=BattleResolution::None;
  BattleRecord bytes{};
  bytes.fill(0xCC);
  const auto unchanged=bytes;
  assert(encode_battle_progress(invalid,bytes)==
         BattleRecordStatus::InvalidValues);
  assert(bytes==unchanged);
  invalid=example();
  invalid.history.victories=0;
  assert(encode_battle_progress(invalid,bytes)==
         BattleRecordStatus::InvalidValues);
  assert(bytes==unchanged);
}
void test_uint32_max_and_independent_from_field_save(){
  auto p=example();
  p.history.victories=std::numeric_limits<std::uint32_t>::max();
  p.history.defeats=std::numeric_limits<std::uint32_t>::max();
  p.history.retreats=std::numeric_limits<std::uint32_t>::max();
  p.rewards.experience=std::numeric_limits<std::uint32_t>::max();
  p.rewards.gella=std::numeric_limits<std::uint32_t>::max();
  BattleRecord bytes{};
  assert(encode_battle_progress(p,bytes)==BattleRecordStatus::Encoded);
  BattleProgress restored{};
  assert(decode_battle_progress(bytes.data(),bytes.size(),restored)==
         BattleRecordStatus::Decoded);
  match(p,restored);
  static_assert(kBattleRecordBytes==36);
  static_assert(kFieldSaveRecordSize==40);
  assert(bytes[0]=='W' && bytes[1]=='A' && bytes[2]=='B' && bytes[3]=='R');
}
void test_account_from_real_battle_session(){
  FieldBattleSession battle{};
  std::vector<std::uint32_t> raw(static_cast<std::size_t>(kRasterWidth)*kRasterHeight);
  PixelTarget target{raw.data(),kRasterWidth,kRasterHeight,kRasterWidth};
  FieldBattleSessionInput start{};start.manual_mode=true;start.open=true;
  assert(advance_battle_session(battle,start,target).entered);
  battle.battle.enemies[0].hp=1;
  battle.battle.enemies[1].hp=1;
  FieldBattleSessionInput attack{};attack.pad.confirm=true;
  assert(advance_battle_session(battle,attack,target).control.status==
         BattleControlStatus::ActionApplied);
  assert(advance_battle_session(battle,{},target).status==
         BattleSceneStatus::Rendered);
  assert(advance_battle_session(battle,attack,target).control.status==
         BattleControlStatus::ActionApplied);
  FieldBattleSessionInput close{};close.close=true;
  assert(advance_battle_session(battle,close,target).resolution==
         BattleResolution::Victory);
  BattleProgress snapshot{battle.history,battle.rewards};
  BattleRecord data{};
  assert(encode_battle_progress(snapshot,data)==BattleRecordStatus::Encoded);
  BattleProgress recovered{};
  assert(decode_battle_progress(data.data(),data.size(),recovered)==
         BattleRecordStatus::Decoded);
  match(snapshot,recovered);
  assert(recovered.history.victories==1);
  assert(recovered.rewards.experience==kPrototypeVictoryExp);
  assert(recovered.rewards.gella==kPrototypeVictoryGella);
}
}
int main(){
  test_empty_and_real_record_roundtrip();
  test_reject_invalid_lengths_magic_version_checksum_atomic();
  test_reserved_and_malformed_values_rejected_even_with_correct_crc();
  test_invalid_encoding_cannot_modify_output();
  test_uint32_max_and_independent_from_field_save();
  test_account_from_real_battle_session();
}
