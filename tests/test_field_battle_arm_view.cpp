#include "field_battle_arm_view.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

using namespace wa::field;

namespace {

constexpr std::uint32_t kSentinel = 0xC0FFEE23u;
constexpr int kStride = kRasterWidth + 12;

struct Frame {
  std::vector<std::uint32_t> pixels = std::vector<std::uint32_t>(
      static_cast<std::size_t>(kStride)*kRasterHeight+37,kSentinel);
  PixelTarget target{pixels.data(),kRasterWidth,kRasterHeight,kStride};
  std::uint32_t at(int x,int y) const {
    return pixels[static_cast<std::size_t>(y)*kStride+
                  static_cast<std::size_t>(x)];
  }
  void check_padding() const {
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<kStride;++x)
        assert(at(x,y)==kSentinel);
    for(std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
        i<pixels.size();++i) assert(pixels[i]==kSentinel);
  }
};

void initial_full_ammo_panel_and_unchanged_core_frame() {
  auto battle=make_demo_battle();BattleCursor cursor{};
  const ArmMagazine mag{};
  Frame f;
  assert(draw_field_battle(f.target,battle,cursor)==BattleRenderStatus::Rendered);
  const auto baseline=f.pixels;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  // Gold outline and complete gold magazine bar.
  assert(f.at(kArmHudX,kArmHudY)==kBattleGold);
  assert(f.at(kArmHudX+20,kArmHudY+38)==kBattleGold);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleGold);
  assert(f.at(kArmHudX+20,kArmHudY+53)==kBattlePanel);
  for(int y=0;y<kRasterHeight;++y)
    for(int x=0;x<kRasterWidth;++x)
      if(x<kArmHudX || x>=kArmHudX+kArmHudWidth ||
         y<kArmHudY || y>=kArmHudY+kArmHudHeight)
        assert(f.at(x,y)==baseline[static_cast<std::size_t>(y)*kStride+x]);
  assert(battle.party[0].hp==24 && battle.enemies[0].hp==14);
  assert(mag.rounds==3 && cursor.actor==0);
  f.check_padding();
}

void spent_ammo_changes_only_its_bar_and_label() {
  auto battle=make_demo_battle();BattleCursor cursor{};
  ArmMagazine mag{2,3,10}; Frame f;
  assert(draw_field_battle(f.target,battle,cursor)==BattleRenderStatus::Rendered);
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  // Floor(220*2/3)=146 pixels; no stale ammo bar remains at right.
  assert(f.at(kArmHudX+20+145,kArmHudY+38)==kBattleGold);
  assert(f.at(kArmHudX+20+146,kArmHudY+38)==kBattleBackground);
  const auto two=f.pixels;
  mag.rounds=0;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  assert(f.at(kArmHudX+20,kArmHudY+38)==kBattleBackground);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleBackground);
  assert(f.at(kArmHudX,kArmHudY)==kBattleGold); // Outline always present.
  assert(f.pixels != two); // Empty status/red glyphs and zero-width bar.
  assert(battle.party[0].hp==24);
  f.check_padding();
}

void bad_target_state_and_magazine_never_touch_any_pixel() {
  auto battle=make_demo_battle(); ArmMagazine mag{}; Frame f;
  const auto untouched=f.pixels;
  auto bad=f.target;
  bad.width=kRasterWidth-1;
  assert(draw_battle_arm_status(bad,battle,mag)==ArmHudStatus::InvalidTarget);
  bad=f.target;bad.stride_pixels=kRasterWidth-1;
  assert(draw_battle_arm_status(bad,battle,mag)==ArmHudStatus::InvalidTarget);
  bad=f.target;bad.pixels=nullptr;
  assert(draw_battle_arm_status(bad,battle,mag)==ArmHudStatus::InvalidTarget);
  battle.party[0].hp=25;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::InvalidBattle);
  battle=make_demo_battle();
  mag.capacity=0;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::InvalidMagazine);
  mag={4,3,10};
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::InvalidMagazine);
  mag={1,3,0};
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::InvalidMagazine);
  assert(f.pixels==untouched);
}

void display_matches_explicit_arm_fire_and_reload_but_never_controls_game() {
  auto battle=make_demo_battle();ArmMagazine mag{1,3,10};
  const auto shot=advance_arm_command(battle,mag,0,ArmCommand::Fire,0);
  assert(shot.step==ArmStep::Applied && shot.battle.inflicted==9);
  assert(mag.rounds==0 && battle.enemies[0].hp==5);
  Frame f;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  assert(f.at(kArmHudX+20,kArmHudY+38)==kBattleBackground);
  assert(mag.rounds==0 && battle.enemies[0].hp==5);
  // Complete the round through ordinary battle commands.
  assert(advance_field_battle(battle,1,BattleMove::Guard).step==BattleStep::Applied);
  assert(advance_field_battle(battle,2,BattleMove::Guard).enemy_turn_completed);
  assert(advance_arm_command(battle,mag,0,ArmCommand::Reload).step==ArmStep::Applied);
  assert(mag.rounds==3);
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleGold);
  f.check_padding();
}

void maximal_capacity_has_bounded_math_and_read_only_render() {
  auto battle=make_demo_battle();ArmMagazine mag{255,255,65535};
  Frame f;
  const auto first=draw_battle_arm_status(f.target,battle,mag);
  assert(first==ArmHudStatus::Rendered);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleGold);
  const auto snapshot=f.pixels;
  assert(draw_battle_arm_status(f.target,battle,mag)==ArmHudStatus::Rendered);
  assert(f.pixels==snapshot);
  assert(mag.rounds==255 && mag.shot_attack==65535);
  f.check_padding();
}

} // namespace

int main() {
  initial_full_ammo_panel_and_unchanged_core_frame();
  spent_ammo_changes_only_its_bar_and_label();
  bad_target_state_and_magazine_never_touch_any_pixel();
  display_matches_explicit_arm_fire_and_reload_but_never_controls_game();
  maximal_capacity_has_bounded_math_and_read_only_render();
}
