#pragma once
// Stage392: pure deterministic selection of old R battle versus opt-in ARM.
// No libnx, disk files, or rendering; test on Intel Mac independently.
namespace wa::field {

struct ArmEntryChoice {
  bool open_regular = false;
  bool open_arm = false;
  bool battle_owns_input = false;
};

// Feature flag is data here, unlike the caller's compile-time #ifdef.
// When disabled, ZL+R MUST still enter the ordinary R battle. A current
// active session always owns inputs, but no R input can start a second one.
[[nodiscard]] constexpr ArmEntryChoice select_arm_battle_entry(
    bool feature_enabled, bool r_just_pressed, bool zl_held,
    bool autoplay, bool regular_active, bool arm_active) noexcept {
  const bool can_open=r_just_pressed && !autoplay &&
      !regular_active && !arm_active;
  const bool optin=can_open && feature_enabled && zl_held;
  const bool regular=can_open && !optin;
  return {regular,optin,regular_active || arm_active || can_open};
}

} // namespace wa::field
