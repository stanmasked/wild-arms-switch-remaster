#include "field_battle_arm_training.hpp"

#include <cassert>
#include <cstring>
#include <limits>
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

void zr_burst_real_session_turn_then_insufficient_ammo_refusal() {
  ArmTrainingSession session{};Frame pixels;
  // A ZR key held while opening the scene is not a gameplay press.
  ArmTrainingInput opening{};
  opening.open=true;opening.manual=true;opening.arm.burst=true;
  assert(advance_arm_training_session(session,opening,pixels.target).entered);
  ArmTrainingInput burst{};burst.arm.burst=true;
  assert(advance_arm_training_session(session,burst,pixels.target).arm.status==
         ArmControlStatus::Idle);
  assert(session.magazine.rounds==3 && session.battle.enemies[0].hp==14);
  neutral(session,pixels);
  const auto shot=advance_arm_training_session(session,burst,pixels.target);
  assert(shot.arm.status==ArmControlStatus::Applied);
  assert(shot.arm.update.battle.inflicted==14);
  assert(session.magazine.rounds==1 && session.battle.enemies[0].hp==0);
  assert(session.cursor.actor==1 && session.cursor.target==1);
  assert(session.battle.party[0].attack==7);
  assert(pixels.at(kArmHudX+20+72,kArmHudY+38)==kBattleGold);
  assert(pixels.at(kArmHudX+20+73,kArmHudY+38)==kBattleBackground);
  for(int i=0;i<5;++i) {
    const auto held=advance_arm_training_session(session,burst,pixels.target);
    assert(held.arm.status==ArmControlStatus::Idle);
    assert(session.magazine.rounds==1);
  }
  neutral(session,pixels);
  ArmTrainingInput strike{};strike.pad.confirm=true;
  assert(advance_arm_training_session(session,strike,pixels.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.enemies[1].hp==13);
  neutral(session,pixels);
  ArmTrainingInput guard{};guard.pad.guard=true;
  assert(advance_arm_training_session(session,guard,pixels.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.round==2 && session.cursor.actor==0);
  neutral(session,pixels);
  const auto before=session.battle;
  const auto refused=advance_arm_training_session(session,burst,pixels.target);
  assert(refused.arm.status==ArmControlStatus::Refused);
  assert(refused.arm.update.step==ArmStep::InsufficientAmmo);
  assert(session.magazine.rounds==1 && !session.battle.acted[0]);
  assert(session.battle.enemies[1].hp==before.enemies[1].hp);
  neutral(session,pixels);
  ArmTrainingInput regular{};regular.arm.fire=true;
  assert(advance_arm_training_session(session,regular,pixels.target).arm.status==
         ArmControlStatus::Applied);
  assert(session.magazine.rounds==0 && session.battle.enemies[1].hp==5);
  ArmTrainingInput close{};close.close=true;
  const auto result=advance_arm_training_session(session,close,pixels.target);
  assert(result.exited && result.resolution==BattleResolution::Retreat);
  assert(session.history.retreats==1 && session.rewards.gella==0);
  pixels.padding_unchanged();
}

void zr_conflicts_require_full_release_before_attacking() {
  ArmTrainingSession session{};Frame pixels;launch(session,pixels);
  ArmTrainingInput both{};both.arm.burst=true;both.arm.fire=true;
  auto result=advance_arm_training_session(session,both,pixels.target);
  assert(result.arm.status==ArmControlStatus::Idle);
  assert(session.magazine.rounds==3 && session.battle.enemies[0].hp==14);
  ArmTrainingInput still_burst{};still_burst.arm.burst=true;
  result=advance_arm_training_session(session,still_burst,pixels.target);
  assert(result.arm.status==ArmControlStatus::Idle);
  neutral(session,pixels);
  ArmTrainingInput conflict_with_melee{};
  conflict_with_melee.arm.burst=true;
  conflict_with_melee.pad.confirm=true;
  result=advance_arm_training_session(session,conflict_with_melee,pixels.target);
  assert(result.arm.status==ArmControlStatus::Idle);
  assert(result.ordinary.status==BattleControlStatus::Idle);
  result=advance_arm_training_session(session,still_burst,pixels.target);
  assert(result.arm.status==ArmControlStatus::Idle);
  neutral(session,pixels);
  result=advance_arm_training_session(session,still_burst,pixels.target);
  assert(result.arm.status==ArmControlStatus::Applied);
  assert(session.magazine.rounds==1 && session.battle.enemies[0].hp==0);
}

// Compare every byte of the exact claim glyph rectangle, not only
// a chosen "8" pixel. The Victory popup clears this region each frame.
void assert_claim_glyphs(const Frame& actual,const char* expected_message) {
  Frame expected;
  fill_raster_rect(expected.target,0,0,kRasterWidth,kRasterHeight,
                   kBattleBackground);
  const auto n=std::strlen(expected_message);
  assert(n>0 && n<64);
  const int width=static_cast<int>((n-1)*13+10);
  const int left=width+440>955 ? 955-width : 440;
  assert(left>=324 && left+width<=955);
  battle_text(expected.target,left,368,expected_message,kBattleGreen);
  for (int y=368;y<382;++y)
    for (int x=324;x<956;++x)
      assert(actual.at(x,y)==expected.at(x,y));
}

void enter_and_finish_custom_arm_victory(ArmTrainingSession& s,Frame& f) {
  launch(s,f);
  s.battle.enemies[0].hp=1;
  s.battle.enemies[1].hp=1;
  ArmTrainingInput fire{};fire.arm.fire=true;
  assert(advance_arm_training_session(s,fire,f.target).arm.status==
         ArmControlStatus::Applied);
  neutral(s,f);
  ArmTrainingInput strike{};strike.pad.confirm=true;
  assert(advance_arm_training_session(s,strike,f.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(s.battle.phase==BattlePhase::Victory);
}

void victory_preview_and_paid_amount_use_same_variable_offer() {
  ArmTrainingSession session{};Frame picture;
  session.victory_offer={4,7};
  enter_and_finish_custom_arm_victory(session,picture);
  assert_claim_glyphs(picture,"B CLAIM EXP 4  GELLA 7");
  assert(session.rewards.experience==0 && session.rewards.gella==0);
  assert(session.history.victories==0);
  picture.padding_unchanged();

  // Read-only Victory UI updates when experimental payout settings
  // change; credit follows that very same offer on confirmed B close.
  session.victory_offer={19,23};
  neutral(session,picture);
  assert_claim_glyphs(picture,"B CLAIM EXP 19  GELLA 23");
  assert(session.rewards.experience==0 && session.rewards.gella==0);

  // The last visible frame still promises 19/23. A balancing change that
  // happens after that render must not silently alter the B-confirmed payout.
  session.victory_offer={27,31};
  ArmTrainingInput close{};close.close=true;
  const auto result=advance_arm_training_session(session,close,picture.target);
  assert(result.exited && result.resolution==BattleResolution::Victory);
  assert(result.payout.experience==19 && result.payout.gella==23);
  assert(session.rewards.experience==19 && session.rewards.gella==23);
  assert(session.history.victories==1);
  assert(!advance_arm_training_session(session,close,picture.target).exited);
  assert(session.rewards.experience==19 && session.rewards.gella==23);
  picture.padding_unchanged();
}

void victory_cannot_be_claimed_before_preview_was_rendered() {
  ArmTrainingSession session{};Frame picture;launch(session,picture);
  session.battle.enemies[0].hp=0;
  session.battle.enemies[1].hp=0;
  session.battle.phase=BattlePhase::Victory;
  const auto unchanged=picture.data;
  ArmTrainingInput close{};close.close=true;
  const auto blocked=advance_arm_training_session(session,close,picture.target);
  assert(blocked.status==ArmTrainingStatus::InvalidState);
  assert(session.active && session.history.victories==0);
  assert(session.rewards.experience==0 && session.rewards.gella==0);
  assert(picture.data==unchanged);

  // Once the actual Victory preview is rendered, B can claim it normally.
  neutral(session,picture);
  assert_claim_glyphs(picture,"B CLAIM EXP 8  GELLA 12");
  const auto claimed=advance_arm_training_session(session,close,picture.target);
  assert(claimed.exited && claimed.payout.experience==8);
  assert(claimed.payout.gella==12);
  assert(session.history.victories==1 && !session.active);
  picture.padding_unchanged();
}

void victory_preview_is_actual_saturated_credit_and_text_never_overflows() {
  const auto maximum=std::numeric_limits<std::uint32_t>::max();
  ArmTrainingSession session{};Frame picture;
  session.victory_offer={20,90};
  session.rewards={maximum-2,maximum-5};
  enter_and_finish_custom_arm_victory(session,picture);
  // Proposed 20/90 but only 2/5 are still actually creditable.
  assert_claim_glyphs(picture,"B CLAIM EXP 2  GELLA 5");
  assert(session.rewards.experience==maximum-2);
  ArmTrainingInput close{};close.close=true;
  const auto capped=advance_arm_training_session(session,close,picture.target);
  assert(capped.payout.experience==2 && capped.payout.gella==5);
  assert(session.rewards.experience==maximum && session.rewards.gella==maximum);
  assert(advance_arm_training_session(session,close,picture.target).payout.gella==0);

  // Once account is full, the preview must show zero and never wrap.
  session.victory_offer={maximum,maximum};
  enter_and_finish_custom_arm_victory(session,picture);
  assert_claim_glyphs(picture,"B CLAIM EXP 0  GELLA 0");
  const auto zero=advance_arm_training_session(session,close,picture.target);
  assert(zero.payout.experience==0 && zero.payout.gella==0);
  assert(session.rewards.experience==maximum && session.rewards.gella==maximum);

  // Worst-case 10-digit values have a 41-glyph label; left-align
  // inside the same Victory popup, never painting beyond its border.
  ArmTrainingSession fresh{};Frame long_picture;
  fresh.victory_offer={maximum,maximum};
  enter_and_finish_custom_arm_victory(fresh,long_picture);
  assert_claim_glyphs(long_picture,
                      "B CLAIM EXP 4294967295  GELLA 4294967295");
  const auto rich=advance_arm_training_session(fresh,close,long_picture.target);
  assert(rich.payout.experience==maximum && rich.payout.gella==maximum);
  long_picture.padding_unchanged();
}
void real_two_bursts_victory_credit_once_and_visible_after_reentry() {
  ArmTrainingSession session{};Frame display;launch(session,display);
  ArmTrainingInput burst{};burst.arm.burst=true;
  auto start=advance_arm_training_session(session,burst,display.target);
  assert(start.arm.status==ArmControlStatus::Applied);
  assert(start.arm.update.battle.inflicted==14);
  assert(session.magazine.rounds==1 && session.battle.enemies[0].hp==0);
  neutral(session,display);

  ArmTrainingInput strike{};strike.pad.confirm=true;
  assert(advance_arm_training_session(session,strike,display.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.enemies[1].hp==13);
  neutral(session,display);

  ArmTrainingInput guard{};guard.pad.guard=true;
  assert(advance_arm_training_session(session,guard,display.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.round==2 && session.cursor.actor==0);
  neutral(session,display);

  ArmTrainingInput reload{};reload.arm.reload=true;
  assert(advance_arm_training_session(session,reload,display.target).arm.status==
         ArmControlStatus::Applied);
  assert(session.magazine.rounds==3);
  neutral(session,display);

  assert(advance_arm_training_session(session,guard,display.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  neutral(session,display);
  assert(advance_arm_training_session(session,guard,display.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(session.battle.round==3 && session.cursor.actor==0);
  neutral(session,display);

  auto finisher=advance_arm_training_session(session,burst,display.target);
  assert(finisher.arm.status==ArmControlStatus::Applied);
  assert(finisher.arm.update.battle.inflicted==13);
  assert(session.magazine.rounds==1 && session.battle.enemies[1].hp==0);
  assert(session.battle.phase==BattlePhase::Victory);
  // Preview is legible ON the Victory frame, still not a credited payout.
  // Battle 5x7 glyph pixels: B, the 8, and the 1/2 in "GELLA 12".
  assert(display.at(320,294)==kBattleGreen);
  assert(display.at(440+2,368)==kBattleGreen);          // B
  assert(display.at(440+12*13+2,368)==kBattleGreen);    // 8
  assert(display.at(440+21*13+4,368)==kBattleGreen);    // 1
  assert(display.at(440+22*13+2,368)==kBattleGreen);    // 2
  assert(display.at(440+23*13,368)==kBattleBackground); // no overflow
  // Backward compatibility: compare every pixel of the verified default
  // 8/12 NeXium claim line, not just the four indicator glyphs.
  assert_claim_glyphs(display,"B CLAIM EXP 8  GELLA 12");
  assert(session.history.victories==0 && session.rewards.experience==0);
  const auto final_picture=display.data;

  ArmTrainingInput leave{};leave.close=true;
  const auto closed=advance_arm_training_session(session,leave,display.target);
  assert(closed.exited && closed.resolution==BattleResolution::Victory);
  assert(closed.payout.experience==8 && closed.payout.gella==12);
  assert(session.history.victories==1 && session.rewards.experience==8);
  assert(session.rewards.gella==12 && !session.active);
  assert(display.data==final_picture);
  assert(!advance_arm_training_session(session,leave,display.target).exited);
  assert(session.rewards.experience==8 && session.rewards.gella==12);

  ArmTrainingInput reenter{};reenter.open=true;reenter.manual=true;
  assert(advance_arm_training_session(session,reenter,display.target).entered);
  assert(session.magazine.rounds==3 && session.battle.enemies[0].hp==14);
  assert(session.battle.enemies[1].hp==17 && session.history.victories==1);
  // The claim prompt is only for an ACTUAL Victory frame, never reentry.
  assert(display.at(440+2,368)!=kBattleGreen);
  assert(display.at(70,667)==kBattleGreen); // "EXP 8  GELLA 12"
  assert(display.at(70,687)==kBattleGold);  // "W 1  L 0  E 0"
  assert(session.rewards.experience==8 && session.rewards.gella==12);
  display.padding_unchanged();

  // Closing the new unwon battle is a retreat, not a second payout.
  const auto retreat=advance_arm_training_session(session,leave,display.target);
  assert(retreat.exited && retreat.resolution==BattleResolution::Retreat);
  assert(retreat.payout.experience==0 && retreat.payout.gella==0);
  assert(session.history.victories==1 && session.history.retreats==1);
  assert(session.rewards.experience==8 && session.rewards.gella==12);
  assert(advance_arm_training_session(session,reenter,display.target).entered);
  assert(display.at(70,667)==kBattleGreen);
  assert(session.rewards.experience==8 && session.rewards.gella==12);
}

// Exercise alternative rewards without any PlayStation/SDMC input.
void finish_dynamic_victory(ArmTrainingSession& s,Frame& pixels) {
  launch(s,pixels);
  s.battle.enemies[0].hp=1;
  s.battle.enemies[1].hp=1;
  ArmTrainingInput shot{};shot.arm.fire=true;
  assert(advance_arm_training_session(s,shot,pixels.target).arm.status==
         ArmControlStatus::Applied);
  neutral(s,pixels);
  ArmTrainingInput melee{};melee.pad.confirm=true;
  assert(advance_arm_training_session(s,melee,pixels.target).ordinary.status==
         BattleControlStatus::ActionApplied);
  assert(s.battle.phase==BattlePhase::Victory);
}

void custom_volatile_reward_offer_is_previewed_and_credited_once() {
  ArmTrainingSession s{};Frame pixels;
  s.victory_offer={19,27};
  finish_dynamic_victory(s,pixels);
  assert_claim_glyphs(pixels,"B CLAIM EXP 19  GELLA 27");
  assert(s.rewards.experience==0 && s.rewards.gella==0);
  ArmTrainingInput leave{};leave.close=true;
  const auto awarded=advance_arm_training_session(s,leave,pixels.target);
  assert(awarded.exited && awarded.payout.experience==19);
  assert(awarded.payout.gella==27);
  assert(s.rewards.experience==19 && s.rewards.gella==27);
  const auto second=advance_arm_training_session(s,leave,pixels.target);
  assert(!second.exited && second.payout.experience==0);
  assert(s.rewards.experience==19 && s.rewards.gella==27);
}

void near_limit_preview_matches_actual_saturated_credit() {
  ArmTrainingSession s{};Frame pixels;
  constexpr auto limit=std::numeric_limits<std::uint32_t>::max();
  s.rewards.experience=limit-3;
  s.rewards.gella=limit-5;
  s.victory_offer={27,43};
  finish_dynamic_victory(s,pixels);
  assert_claim_glyphs(pixels,"B CLAIM EXP 3  GELLA 5");
  assert(s.rewards.experience==limit-3 && s.rewards.gella==limit-5);
  ArmTrainingInput leave{};leave.close=true;
  const auto paid=advance_arm_training_session(s,leave,pixels.target);
  assert(paid.exited && paid.payout.experience==3 && paid.payout.gella==5);
  assert(s.rewards.experience==limit && s.rewards.gella==limit);
}

void maximum_decimal_reward_preview_is_inside_victory_frame() {
  ArmTrainingSession s{};Frame pixels;
  constexpr auto limit=std::numeric_limits<std::uint32_t>::max();
  s.victory_offer={limit,limit};
  finish_dynamic_victory(s,pixels);
  assert_claim_glyphs(pixels,
    "B CLAIM EXP 4294967295  GELLA 4294967295");
  assert(s.rewards.experience==0 && s.rewards.gella==0);
}

} // namespace

int main() {
  explicit_entry_and_hidden_frame_isolation();
  held_open_fire_and_consecutive_turn_actions();
  mixed_arm_and_normal_input_never_produces_late_attack();
  victory_award_once_on_close_without_persistence_or_pixels();
  retreat_has_no_payout_and_does_not_change_backing_frame();
  damaged_target_and_magazine_never_consume_input_or_write();
  zr_burst_real_session_turn_then_insufficient_ammo_refusal();
  zr_conflicts_require_full_release_before_attacking();
  real_two_bursts_victory_credit_once_and_visible_after_reentry();
  victory_preview_and_paid_amount_use_same_variable_offer();
  victory_cannot_be_claimed_before_preview_was_rendered();
  victory_preview_is_actual_saturated_credit_and_text_never_overflows();
  custom_volatile_reward_offer_is_previewed_and_credited_once();
  near_limit_preview_matches_actual_saturated_credit();
  maximum_decimal_reward_preview_is_inside_victory_frame();
}
