#include "field_battle_session.hpp"

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

using namespace wa::field;

namespace {
constexpr std::uint32_t kCanary = 0xDEADC0DEu;
constexpr int kStride = kRasterWidth + 8;
struct Frame {
  std::vector<std::uint32_t> bytes = std::vector<std::uint32_t>(
      static_cast<std::size_t>(kStride) * kRasterHeight + 32, kCanary);
  PixelTarget target{bytes.data(), kRasterWidth, kRasterHeight, kStride};
  std::uint32_t pixel(int x, int y) const {
    return bytes[static_cast<std::size_t>(y) * kStride +
                 static_cast<std::size_t>(x)];
  }
  void check_guards() const {
    for (int y = 0; y < kRasterHeight; ++y)
      for (int x = kRasterWidth; x < kStride; ++x)
        assert(pixel(x,y) == kCanary);
    for (std::size_t i = static_cast<std::size_t>(kStride) * kRasterHeight;
         i < bytes.size(); ++i)
      assert(bytes[i] == kCanary);
  }
};

void test_inactive_does_not_draw_or_attack() {
  FieldBattleSession session{};
  Frame f;
  const auto before = f.bytes;
  FieldBattleSessionInput input{};
  input.pad.confirm = true;
  assert(advance_battle_session(session,input,f.target).status ==
         BattleSceneStatus::Inactive);
  input.open = true;  // autoplay must not open a battle
  assert(advance_battle_session(session,input,f.target).status ==
         BattleSceneStatus::Inactive);
  assert(!session.active && session.battle.enemies[0].hp == 14);
  assert(f.bytes == before);
}

void test_opening_press_is_not_an_attack() {
  FieldBattleSession session{};
  Frame f;
  FieldBattleSessionInput open{};
  open.manual_mode = true;
  open.open = true;
  open.pad.confirm = true;  // R+A on the same Switch frame.
  auto step = advance_battle_session(session,open,f.target);
  assert(step.status == BattleSceneStatus::Rendered && step.entered);
  assert(session.active && session.cursor.previous.confirm);
  assert(session.battle.enemies[0].hp == 14);
  assert(f.pixel(70,120) == kBattleBlue);
  f.check_guards();

  FieldBattleSessionInput held{};
  held.pad.confirm = true; // Holding A may not strike later.
  step = advance_battle_session(session,held,f.target);
  assert(step.status == BattleSceneStatus::Rendered);
  assert(step.control.status == BattleControlStatus::Idle);
  assert(session.battle.enemies[0].hp == 14);

  held.pad = {};
  assert(advance_battle_session(session,held,f.target).status ==
         BattleSceneStatus::Rendered);
  held.pad.confirm = true;
  step = advance_battle_session(session,held,f.target);
  assert(step.control.status == BattleControlStatus::ActionApplied);
  assert(step.control.action.inflicted == 6);
  assert(session.battle.enemies[0].hp == 8);
  assert(session.cursor.actor == 1);
  // The first enemy health bar contracted from 340px to 194px.
  assert(f.pixel(692 + 210,249) == kBattleBackground);
  assert(f.pixel(692 + 180,249) == kBattleRed);
}

void test_hold_strike_does_not_repeat() {
  FieldBattleSession session{};
  Frame f;
  FieldBattleSessionInput open{};
  open.manual_mode = true;
  open.open = true;
  assert(advance_battle_session(session,open,f.target).entered);
  FieldBattleSessionInput attack{};
  attack.pad.confirm = true;
  assert(advance_battle_session(session,attack,f.target).control.status ==
         BattleControlStatus::ActionApplied);
  const auto hp = session.battle.enemies[0].hp;
  assert(advance_battle_session(session,attack,f.target).control.status ==
         BattleControlStatus::Idle);
  assert(session.battle.enemies[0].hp == hp);
}

void test_close_restores_underlying_frame_and_reopen_resets_battle() {
  FieldBattleSession session{};
  Frame f;
  FieldBattleSessionInput open{};
  open.manual_mode = true;
  open.open = true;
  assert(advance_battle_session(session,open,f.target).entered);
  FieldBattleSessionInput action{};
  action.pad.guard = true;
  assert(advance_battle_session(session,action,f.target).control.status ==
         BattleControlStatus::ActionApplied);
  assert(session.battle.acted[0]);
  // Simulate the field engine's newly drawn frame; closing the overlay
  // must not write a single additional pixel.
  std::fill(f.bytes.begin(),f.bytes.end(),kCanary);
  const auto baseline=f.bytes;
  FieldBattleSessionInput leave{};
  leave.close=true;
  auto frame=advance_battle_session(session,leave,f.target);
  assert(frame.status==BattleSceneStatus::Inactive && frame.exited);
  assert(!session.active && f.bytes==baseline);
  // A later new encounter uses fresh statistics, not a previous guard.
  assert(advance_battle_session(session,open,f.target).entered);
  assert(!session.battle.acted[0] && !session.battle.guarding[0]);
  assert(session.battle.enemies[0].hp==14);
  f.check_guards();
}

void test_corruption_never_writes_or_consumes_buttons() {
  FieldBattleSession session{};
  Frame f;
  FieldBattleSessionInput open{};
  open.manual_mode=true;open.open=true;open.pad.confirm=true;
  const auto before=f.bytes;
  auto invalid=f.target;invalid.width=kRasterWidth-1;
  assert(advance_battle_session(session,open,invalid).status ==
         BattleSceneStatus::InvalidTarget);
  assert(!session.active && !session.cursor.previous.confirm);
  assert(f.bytes==before);
  assert(advance_battle_session(session,open,f.target).entered);
  std::fill(f.bytes.begin(),f.bytes.end(),kCanary);
  const auto second=f.bytes;
  session.battle.party[0].hp=25;
  FieldBattleSessionInput attack{};
  attack.pad.confirm=true;
  assert(advance_battle_session(session,attack,f.target).status ==
         BattleSceneStatus::InvalidBattle);
  assert(session.cursor.previous.confirm && f.bytes==second);
  session.battle=make_demo_battle();
  session.cursor.actor=kBattlePartySize;
  assert(advance_battle_session(session,attack,f.target).status ==
         BattleSceneStatus::InvalidBattle);
  assert(f.bytes==second);
}

void test_completed_battle_can_only_be_closed() {
  FieldBattleSession session{};
  Frame f;
  FieldBattleSessionInput open{};
  open.manual_mode=true;open.open=true;
  assert(advance_battle_session(session,open,f.target).entered);
  session.battle.enemies[0].hp=0;
  session.battle.enemies[1].hp=0;
  session.battle.phase=BattlePhase::Victory;
  FieldBattleSessionInput attack{};attack.pad.confirm=true;
  auto frame=advance_battle_session(session,attack,f.target);
  assert(frame.status==BattleSceneStatus::Rendered);
  assert(frame.control.status==BattleControlStatus::Idle);
  assert(f.pixel(320,294)==kBattleGreen);
  assert(!session.battle.acted[0]);
  FieldBattleSessionInput close{};close.close=true;
  assert(advance_battle_session(session,close,f.target).exited);
}
} // namespace

int main() {
  test_inactive_does_not_draw_or_attack();
  test_opening_press_is_not_an_attack();
  test_hold_strike_does_not_repeat();
  test_close_restores_underlying_frame_and_reopen_resets_battle();
  test_corruption_never_writes_or_consumes_buttons();
  test_completed_battle_can_only_be_closed();
}
