#include "field_battle.hpp"
#include <cassert>
#include <cstddef>
#include <cstdint>
using namespace wa::field;
namespace {
void equal(const FieldBattle& a,const FieldBattle& b) {
  assert(a.round==b.round && a.phase==b.phase);
  for(std::size_t i=0;i<kBattlePartySize;++i) {
    assert(a.party[i].hp==b.party[i].hp);
    assert(a.party[i].max_hp==b.party[i].max_hp);
    assert(a.party[i].attack==b.party[i].attack);
    assert(a.party[i].armor==b.party[i].armor);
    assert(a.acted[i]==b.acted[i] && a.guarding[i]==b.guarding[i]);
  }
  for(std::size_t i=0;i<kBattleEnemyCount;++i) {
    assert(a.enemies[i].hp==b.enemies[i].hp);
    assert(a.enemies[i].max_hp==b.enemies[i].max_hp);
    assert(a.enemies[i].attack==b.enemies[i].attack);
    assert(a.enemies[i].armor==b.enemies[i].armor);
  }
}
void attack_and_atomic_invalid_choices() {
  auto b=make_demo_battle();
  assert(valid_field_battle(b));
  auto r=advance_field_battle(b,0,BattleMove::Strike,0);
  assert(r.step==BattleStep::Applied && r.inflicted==6);
  assert(b.enemies[0].hp==8 && b.acted[0] && b.round==1);
  const auto previous=b;
  assert(advance_field_battle(b,0,BattleMove::Strike,0).step==BattleStep::InvalidChoice);
  assert(advance_field_battle(b,1,BattleMove::Strike,2).step==BattleStep::InvalidChoice);
  assert(advance_field_battle(b,4,BattleMove::Guard).step==BattleStep::InvalidChoice);
  assert(advance_field_battle(b,1,BattleMove::Guard,1).step==BattleStep::InvalidChoice);
  equal(b,previous);
}
void guarding_and_round_cycle() {
  auto b=make_demo_battle();
  assert(advance_field_battle(b,0,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(b,2,BattleMove::Strike,1).step==BattleStep::Applied);
  const auto r=advance_field_battle(b,1,BattleMove::Strike,1);
  assert(r.step==BattleStep::Applied && r.enemy_turn_completed);
  assert(r.retaliation[0]==2 && r.retaliation[1]==5 && r.retaliation[2]==0);
  assert(b.party[0].hp==22 && b.party[1].hp==15);
  assert(b.phase==BattlePhase::Player && b.round==2);
  for(std::size_t i=0;i<kBattlePartySize;++i) assert(!b.acted[i] && !b.guarding[i]);
}
void victory_no_retaliation() {
  auto b=make_demo_battle();
  b.enemies[0].hp=b.enemies[1].hp=1;
  assert(advance_field_battle(b,0,BattleMove::Strike,0).inflicted==1);
  const auto r=advance_field_battle(b,1,BattleMove::Strike,1);
  assert(r.inflicted==1 && r.phase==BattlePhase::Victory);
  assert(!r.enemy_turn_completed && b.party[0].hp==24 && b.round==1);
  const auto frozen=b;
  assert(advance_field_battle(b,2,BattleMove::Guard).step==BattleStep::InvalidChoice);
  equal(b,frozen);
}
void defeat_skips_fallen_heroes() {
  auto b=make_demo_battle();
  for(auto& p:b.party) p.hp=1;
  assert(advance_field_battle(b,0,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(b,1,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(b,2,BattleMove::Guard).enemy_turn_completed);
  assert(b.round==2 && b.party[0].hp==0 && b.party[1].hp==0 && b.party[2].hp==1);
  const auto r=advance_field_battle(b,2,BattleMove::Guard);
  assert(r.enemy_turn_completed && b.phase==BattlePhase::Defeat);
}
void corruption_and_overflow_atomicity() {
  auto b=make_demo_battle(), invalid=b;
  invalid.party[1].hp=21;
  const auto broken=invalid;
  assert(advance_field_battle(invalid,0,BattleMove::Strike).step==BattleStep::InvalidState);
  equal(invalid,broken);
  invalid=b; invalid.guarding[0]=true;
  assert(!valid_field_battle(invalid));
  invalid=b; invalid.round=0;
  assert(!valid_field_battle(invalid));
  const auto unchanged=b;
  assert(advance_field_battle(b,0,static_cast<BattleMove>(99)).step==BattleStep::InvalidChoice);
  equal(b,unchanged);
  b.round=UINT32_MAX;
  assert(advance_field_battle(b,0,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(b,1,BattleMove::Guard).step==BattleStep::Applied);
  const auto before_last=b;
  assert(advance_field_battle(b,2,BattleMove::Guard).step==BattleStep::InvalidState);
  equal(b,before_last);
}
void damage_and_determinism() {
  assert(battle_damage(0,65000,false)==1);
  assert(battle_damage(0,65000,true)==1);
  assert(battle_damage(65535,0,true)==32768);
  auto a=make_demo_battle(),b=a;
  for(int round=0;round<2;++round) {
    for(std::size_t actor=0;actor<kBattlePartySize;++actor) {
      auto action=actor==0?BattleMove::Guard:BattleMove::Strike;
      auto target=actor==2?1u:0u;
      auto x=advance_field_battle(a,actor,action,target);
      auto y=advance_field_battle(b,actor,action,target);
      assert(x.step==y.step && x.inflicted==y.inflicted);
      assert(x.enemy_turn_completed==y.enemy_turn_completed);
      for(std::size_t k=0;k<kBattlePartySize;++k)
        assert(x.retaliation[k]==y.retaliation[k]);
      equal(a,b);
    }
  }
}
}
int main() {
  attack_and_atomic_invalid_choices();
  guarding_and_round_cycle();
  victory_no_retaliation();
  defeat_skips_fallen_heroes();
  corruption_and_overflow_atomicity();
  damage_and_determinism();
}
