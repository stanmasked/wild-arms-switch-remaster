#include "field_battle_arm_training.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

using namespace wa::field;

namespace {
constexpr int kStride=kRasterWidth+9;
constexpr std::uint32_t kCanary=0x7F2034AAu;

struct Frame {
  std::vector<std::uint32_t> data=std::vector<std::uint32_t>(
    static_cast<std::size_t>(kStride)*kRasterHeight+13,kCanary);
  PixelTarget target{data.data(),kRasterWidth,kRasterHeight,kStride};
  std::uint32_t at(int x,int y) const {
    return data[static_cast<std::size_t>(y)*kStride+
                static_cast<std::size_t>(x)];
  }
  void padding_unchanged() const {
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<kStride;++x) assert(at(x,y)==kCanary);
    for(std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
        i<data.size();++i) assert(data[i]==kCanary);
  }
};

void launch(ArmTrainingSession& session,Frame& pixels) {
  ArmTrainingInput open{};
  open.open=true;open.manual=true;
  const auto frame=advance_arm_training_session(session,open,pixels.target);
  assert(frame.status==ArmTrainingStatus::Rendered && frame.entered);
  assert(session.active && session.magazine.rounds==3);
}
void neutral(ArmTrainingSession& session,Frame& pixels) {
  assert(advance_arm_training_session(session,{},pixels.target).status==
         ArmTrainingStatus::Rendered);
}

void explicit_entry_and_hidden_frame_isolation() {
  ArmTrainingSession session{};
  Frame f,ordinary;
  const auto untouched=f.data;
  ArmTrainingInput blocked{};
  blocked.open=true; // Autoplay / non-manual must not enter.
  assert(advance_arm_training_session(session,blocked,f.target).status==
         ArmTrainingStatus::Inactive);
  assert(!session.active && f.data==untouched);
  const auto battle=make_demo_battle(); BattleCursor cursor{};
  assert(draw_field_battle(ordinary.target,battle,cursor)==
         BattleRenderStatus::Rendered);
  launch(session,f);
  assert(f.at(kArmHudX,kArmHudY)==kBattleGold);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleGold);
  for(int y=0;y<kRasterHeight;++y)
    for(int x=0;x<kRasterWidth;++x)
      if(x<kArmHudX || x>=kArmHudX+kArmHudWidth ||
         y<kArmHudY || y>=kArmHudY+kArmHudHeight)
        assert(f.at(x,y)==ordinary.at(x,y));
  assert(session.history.victories==0 && session.rewards.gella==0);
  f.padding_unchanged();
}

void held_open_fire_and_consecutive_turn_actions() {
  ArmTrainingSession session{};Frame f;
  ArmTrainingInput first{};
  first.manual=true;first.open=true;first.arm.fire=true;
  assert(advance_arm_training_session(session,first,f.target).entered);
  assert(session.battle.enemies[0].hp==14);
  ArmTrainingInput held{};held.arm.fire=true;
  assert(advance_arm_training_session(session,held,f.target).arm.status==
         ArmControlStatus::Idle);
  assert(session.magazine.rounds==3);
  neutral(session,f);
  const auto fired=advance_arm_training_session(session,held,f.target);
  assert(fired.arm.status==ArmControlStatus::Applied);
  assert(fired.arm.update.battle.inflicted==9);
  assert(session.battle.enemies[0].hp==5 && session.magazine.rounds==2);
  assert(session.cursor.actor==1 && session.battle.party[0].attack==7);
  // Holding Fire never repeats during a subsequent hero's turn.
  for(int i=0;i<3;++i)
    assert(advance_arm_training_session(session,held,f.target).arm.status==
           ArmControlStatus::Idle);
  neutral(session,f);
  ArmTrainingInput strike{};strike.pad.confirm=true;
  const auto regular=advance_arm_training_session(session,strike,f.target);
  assert(regular.ordinary.status==BattleControlStatus::ActionApplied);
  assert(session.battle.enemies[0].hp==0 && session.cursor.target==1);
  neutral(session,f);
  ArmTrainingInput guard{};guard.pad.guard=true;
  assert(advance_arm_training_session(session,guard,f.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.round==2 && session.cursor.actor==0);
  neutral(session,f);
  ArmTrainingInput reload{};reload.arm.reload=true;
  const auto restored=advance_arm_training_session(session,reload,f.target);
  assert(restored.arm.status==ArmControlStatus::Applied);
  assert(session.magazine.rounds==3 && session.battle.acted[0]);
  assert(!session.battle.guarding[0]);
  assert(f.at(kArmHudX+20+219,kArmHudY+38)==kBattleGold);
  f.padding_unchanged();
}

void mixed_arm_and_normal_input_never_produces_late_attack() {
  ArmTrainingSession session{};Frame f;launch(session,f);
  ArmTrainingInput both{};both.arm.fire=true;both.pad.confirm=true;
  auto result=advance_arm_training_session(session,both,f.target);
  assert(result.ordinary.status==BattleControlStatus::Idle);
  assert(result.arm.status==ArmControlStatus::Idle);
  assert(session.magazine.rounds==3 && session.battle.enemies[0].hp==14);
  ArmTrainingInput still_held{};still_held.arm.fire=true;
  result=advance_arm_training_session(session,still_held,f.target);
  assert(result.arm.status==ArmControlStatus::Idle);
  assert(session.magazine.rounds==3 && !session.battle.acted[0]);
  neutral(session,f);
  result=advance_arm_training_session(session,still_held,f.target);
  assert(result.arm.status==ArmControlStatus::Applied);
  assert(session.magazine.rounds==2);
}

void victory_award_once_on_close_without_persistence_or_pixels() {
  ArmTrainingSession session{};Frame f;launch(session,f);
  session.battle.enemies[0].hp=1;
  session.battle.enemies[1].hp=1;
  ArmTrainingInput fire{};fire.arm.fire=true;
  assert(advance_arm_training_session(session,fire,f.target).arm.status==
         ArmControlStatus::Applied);
  assert(session.battle.enemies[0].hp==0 && session.magazine.rounds==2);
  neutral(session,f);
  ArmTrainingInput strike{};strike.pad.confirm=true;
  assert(advance_arm_training_session(session,strike,f.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.phase==BattlePhase::Victory);
  const auto rendered=f.data;
  ArmTrainingInput leave{};leave.close=true;
  const auto closed=advance_arm_training_session(session,leave,f.target);
  assert(closed.status==ArmTrainingStatus::Inactive && closed.exited);
  assert(closed.resolution==BattleResolution::Victory);
  assert(closed.payout.experience==8 && closed.payout.gella==12);
  assert(!session.active && session.history.victories==1);
  assert(session.rewards.experience==8 && session.rewards.gella==12);
  assert(f.data==rendered);
  assert(!advance_arm_training_session(session,leave,f.target).exited);
  assert(session.rewards.experience==8 && session.history.victories==1);
  ArmTrainingInput reopen{};reopen.open=true;reopen.manual=true;
  assert(advance_arm_training_session(session,reopen,f.target).entered);
  assert(session.magazine.rounds==3 && session.battle.enemies[0].hp==14);
  assert(session.history.victories==1 && session.rewards.gella==12);
}

void retreat_has_no_payout_and_does_not_change_backing_frame() {
  ArmTrainingSession session{};Frame f;launch(session,f);
  const auto before=f.data;
  ArmTrainingInput leave{};leave.close=true;
  const auto closed=advance_arm_training_session(session,leave,f.target);
  assert(closed.exited && closed.resolution==BattleResolution::Retreat);
  assert(closed.payout.experience==0 && closed.payout.gella==0);
  assert(session.history.retreats==1 && session.rewards.gella==0);
  assert(f.data==before);
  f.padding_unchanged();
}

void damaged_target_and_magazine_never_consume_input_or_write() {
  ArmTrainingSession session{};Frame f;
  const auto pristine=f.data;
  ArmTrainingInput open{};open.open=true;open.manual=true;open.arm.fire=true;
  auto broken=f.target;broken.width=kRasterWidth-1;
  assert(advance_arm_training_session(session,open,broken).status==
         ArmTrainingStatus::InvalidTarget);
  assert(!session.active && !session.arm_edges.previous.fire);
  assert(f.data==pristine);
  assert(advance_arm_training_session(session,open,f.target).entered);
  const auto rendered=f.data;
  session.magazine.capacity=0;
  ArmTrainingInput invalid{};invalid.arm.reload=true;
  assert(advance_arm_training_session(session,invalid,f.target).status==
         ArmTrainingStatus::InvalidState);
  assert(!session.arm_edges.previous.reload && f.data==rendered);
  session.magazine.capacity=3;
  broken=f.target;broken.stride_pixels=kRasterWidth-1;
  assert(advance_arm_training_session(session,invalid,broken).status==
         ArmTrainingStatus::InvalidTarget);
  assert(!session.arm_edges.previous.reload && f.data==rendered);
  assert(session.magazine.rounds==3 && !session.battle.acted[0]);
  f.padding_unchanged();
}

} // namespace

int main() {
  explicit_entry_and_hidden_frame_isolation();
  held_open_fire_and_consecutive_turn_actions();
  mixed_arm_and_normal_input_never_produces_late_attack();
  victory_award_once_on_close_without_persistence_or_pixels();
  retreat_has_no_payout_and_does_not_change_backing_frame();
  damaged_target_and_magazine_never_consume_input_or_write();
}
