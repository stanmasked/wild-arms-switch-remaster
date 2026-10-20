#pragma once
// Stage388: opt-in HOST-ONLY integrated ARM battle screen.
// Never called by Nintendo Switch main.cpp; WABJ v1 is unchanged.
#include "field_battle_arm_controller.hpp"
#include "field_battle_arm_view.hpp"
#include "field_battle_rewards.hpp"

#include <cstdint>

namespace wa::field {

struct ArmTrainingSession {
  FieldBattle battle=make_demo_battle();
  BattleCursor cursor{};
  ArmMagazine magazine{};
  ArmEdgeState arm_edges{};
  BattleHistory history{};
  BattleRewardAccount rewards{};
  bool active=false;
};

struct ArmTrainingInput {
  bool open=false;    // Explicit opt-in, manual mode only.
  bool close=false;   // Single B edge supplied by external caller.
  bool manual=false;
  BattlePad pad{};    // Existing A strike, Y guard, D-pad select.
  ArmButtons arm{};   // NEW experiment-only fire/reload controls.
};

enum class ArmTrainingStatus : std::uint8_t {
  Inactive, Rendered, InvalidTarget, InvalidState, InvalidController
};

struct ArmTrainingFrame {
  ArmTrainingStatus status=ArmTrainingStatus::Inactive;
  bool entered=false;
  bool exited=false;
  BattleControlFrame ordinary{};
  ArmControlFrame arm{};
  BattleResolution resolution=BattleResolution::None;
  BattleRewardPayout payout{};
};

[[nodiscard]] inline bool arm_training_target_valid(
    const PixelTarget& target) noexcept {
  return target.pixels!=nullptr &&
         target.width==kRasterWidth && target.height==kRasterHeight &&
         target.stride_pixels>=kRasterWidth &&
         target.stride_pixels<=8192;
}

// A complete, independent training screen connecting ARM rules, input,
// pixel HUD, and VOLATILE battle outcomes. No disk I/O, no libnx mapping.
// Frame errors never commit state or draw partial pixels. Closing renders
// nothing and awards synthetic EXP/Gella once, only after a real victory.
[[nodiscard]] inline ArmTrainingFrame advance_arm_training_session(
    ArmTrainingSession& current, const ArmTrainingInput& input,
    const PixelTarget& target) noexcept {
  if (!current.active && (!input.open || !input.manual || input.close))
    return {};
  ArmTrainingSession next=current;
  const bool entering=!current.active;
  if (entering) {
    next.battle=make_demo_battle();
    next.cursor=BattleCursor{};
    next.magazine=ArmMagazine{};
    next.arm_edges=ArmEdgeState{};
    // Opening buttons must be released before becoming gameplay edges.
    next.cursor.previous=input.pad;
    next.arm_edges.previous=input.arm;
    next.active=true;
  } else {
    if (!valid_field_battle(next.battle) ||
        !valid_arm_magazine(next.magazine) ||
        next.cursor.actor>=kBattlePartySize ||
        next.cursor.target>=kBattleEnemyCount)
      return {ArmTrainingStatus::InvalidState};
    if (input.close) {
      const auto resolution=record_battle_exit(next.history,next.battle.phase);
      const auto payout=credit_battle_reward(next.rewards,resolution);
      next.active=false;
      current=next;
      return {ArmTrainingStatus::Inactive,false,true,{},{},resolution,payout};
    }
  }
  // Preflight before processing ANY input or painting ANY pixel.
  if (!arm_training_target_valid(target))
    return {ArmTrainingStatus::InvalidTarget};

  ArmTrainingFrame frame{};
  if (!entering) {
    const bool has_arm=input.arm.fire || input.arm.reload;
    const bool has_pad=input.pad.left || input.pad.right ||
                       input.pad.up || input.pad.down ||
                       input.pad.confirm || input.pad.guard;
    if (has_arm && has_pad) {
      // Conflict consumes both physical input families; never defers an
      // unintended attack until the other button is released.
      next.cursor.previous=input.pad;
      next.arm_edges.previous=input.arm;
    } else if (has_arm) {
      next.cursor.previous=input.pad;
      frame.arm=advance_arm_controller(
          next.battle,next.magazine,next.cursor,next.arm_edges,input.arm);
      if (frame.arm.status==ArmControlStatus::InvalidState)
        return {ArmTrainingStatus::InvalidController};
    } else {
      // Release ARM latches even while A/Y or D-pad are used.
      next.arm_edges.previous=input.arm;
      frame.ordinary=advance_battle_controller(
          next.battle,next.cursor,input.pad);
      if (frame.ordinary.status==BattleControlStatus::InvalidState)
        return {ArmTrainingStatus::InvalidController};
    }
  }
  // Both renderers are validated before writing. The optional panel
  // cannot fail after an ordinary render of a valid battle/magazine.
  if (!valid_field_battle(next.battle) ||
      !valid_arm_magazine(next.magazine) ||
      next.cursor.actor>=kBattlePartySize ||
      next.cursor.target>=kBattleEnemyCount)
    return {ArmTrainingStatus::InvalidState};
  if (draw_field_battle(target,next.battle,next.cursor)!=
      BattleRenderStatus::Rendered)
    return {ArmTrainingStatus::InvalidState};
  (void)draw_battle_arm_status(target,next.battle,next.magazine);
  draw_previous_battle_history(target,next.history);

  next.active=true;
  current=next;
  frame.status=ArmTrainingStatus::Rendered;
  frame.entered=entering;
  return frame;
}

} // namespace wa::field
