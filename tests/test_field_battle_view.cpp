#include "field_battle_view.hpp"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

using namespace wa::field;
namespace {
constexpr std::uint32_t sentinel=0xBADCAFEu;
constexpr int stride=kRasterWidth+16;
struct View {
  std::vector<std::uint32_t> data=std::vector<std::uint32_t>(
    static_cast<std::size_t>(stride)*kRasterHeight+64,sentinel);
  PixelTarget target{data.data(),kRasterWidth,kRasterHeight,stride};
  std::uint32_t at(int x,int y) const {
    return data[static_cast<std::size_t>(y)*stride+static_cast<std::size_t>(x)];
  }
  void guards() const {
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<stride;++x) assert(at(x,y)==sentinel);
    for(std::size_t i=static_cast<std::size_t>(stride)*kRasterHeight;i<data.size();++i)
      assert(data[i]==sentinel);
  }
};
void test_initial_selection_and_health() {
  auto b=make_demo_battle(); BattleCursor c{}; View v;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::Rendered);
  assert(v.at(70,120)==kBattleBlue); // selected hero
  assert(v.at(70,284)!=kBattleBlue); // other hero not selected
  assert(v.at(670,165)==kBattleGold); // targeted foe
  assert(v.at(670,407)!=kBattleGold); // non-targeted foe
  assert(v.at(92,199)==kBattleGreen); // 24/24 full bar
  assert(v.at(431,199)==kBattleGreen);
  assert(v.at(92,249)==kBattlePanel);
  assert(v.at(692,249)==kBattleRed);
  assert(v.at(20,705)==rgba(28,40,57));
  v.guards();
}
void test_change_selection_damage_and_empty_health() {
  auto b=make_demo_battle(); BattleCursor c{};
  c.actor=2;c.target=1;
  b.party[0].hp=12;b.enemies[0].hp=0;
  View v;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::Rendered);
  assert(v.at(70,448)==kBattleBlue);
  assert(v.at(670,407)==kBattleGold);
  assert(v.at(92+169,199)==kBattleGreen);
  assert(v.at(92+171,199)==kBattleBackground);
  assert(v.at(692,249)==kBattleBackground);
  assert(v.at(692,491)==kBattleRed);
  assert(v.at(670,165)!=kBattleGold);
  v.guards();
}
void test_render_is_read_only_and_repeatable() {
  auto b=make_demo_battle();BattleCursor c{};
  View v,w;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::Rendered);
  assert(draw_field_battle(w.target,b,c)==BattleRenderStatus::Rendered);
  assert(v.data==w.data);
  assert(b.party[0].hp==24 && b.enemies[0].hp==14 && c.actor==0 && c.target==0);
  v.guards();w.guards();
}
void test_bad_inputs_never_touch_buffer() {
  auto b=make_demo_battle();BattleCursor c{}; View v;
  auto before=v.data;
  assert(draw_field_battle({nullptr,kRasterWidth,kRasterHeight,stride},b,c)==
         BattleRenderStatus::InvalidTarget);
  assert(draw_field_battle({v.data.data(),kRasterWidth,kRasterHeight,kRasterWidth-1},b,c)==
         BattleRenderStatus::InvalidTarget);
  assert(draw_field_battle({v.data.data(),kRasterWidth-1,kRasterHeight,stride},b,c)==
         BattleRenderStatus::InvalidTarget);
  b.party[0].hp=25;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::InvalidBattle);
  b=make_demo_battle(); c.target=2;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::InvalidCursor);
  c.target=0;c.actor=3;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::InvalidCursor);
  assert(before==v.data);
}
void test_result_overlay() {
  auto b=make_demo_battle();BattleCursor c{}; View v;
  b.enemies[0].hp=b.enemies[1].hp=0;
  b.phase=BattlePhase::Victory;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::Rendered);
  assert(v.at(320,294)==kBattleGreen);
  assert(v.at(325,300)==kBattleBackground);
  b=make_demo_battle();
  for(auto& p:b.party)p.hp=0;
  b.phase=BattlePhase::Defeat;
  assert(draw_field_battle(v.target,b,c)==BattleRenderStatus::Rendered);
  assert(v.at(320,294)==kBattleRed);
  v.guards();
}
void test_glyph_contract() {
  for(const char* p="BATTLE PROTOTYPE ROUND PARTY ENEMIES HERO FOE HP READY ACTED GUARD DOWN ACTIVE VICTORY DEFEAT A STRIKE Y GUARD D PAD SELECT";*p;++p){
    if(*p==' ')continue;
    bool lit=false;
    for(auto r:battle_font(*p))if(r)lit=true;
    assert(lit);
  }
  for(char ch='0';ch<='9';++ch){
    bool lit=false;
    for(auto r:battle_font(ch))if(r)lit=true;
    assert(lit);
  }
}
}
int main(){
  test_initial_selection_and_health();
  test_change_selection_damage_and_empty_health();
  test_render_is_read_only_and_repeatable();
  test_bad_inputs_never_touch_buffer();
  test_result_overlay();
  test_glyph_contract();
}
