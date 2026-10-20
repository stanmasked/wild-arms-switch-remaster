#include "field_battle_arm_entry.hpp"

#include <cassert>
#include <initializer_list>

using namespace wa::field;

namespace {
void complete_truth_table_six_input_flags() {
  // Exhaustive 2^6 routing combinations, including impossible simultaneous
  // active scenes. An illegal combination must never spawn another battle.
  unsigned cases=0;
  for(int mask=0;mask<64;++mask) {
    const bool feature=(mask&1)!=0;
    const bool fresh_r=(mask&2)!=0;
    const bool zl=(mask&4)!=0;
    const bool autoplay=(mask&8)!=0;
    const bool regular_active=(mask&16)!=0;
    const bool arm_active=(mask&32)!=0;
    const ArmEntryChoice out=select_arm_battle_entry(
        feature,fresh_r,zl,autoplay,regular_active,arm_active);
    const bool can_open=fresh_r && !autoplay &&
        !regular_active && !arm_active;
    assert(!(out.open_regular && out.open_arm));
    assert(out.open_arm == (can_open && feature && zl));
    assert(out.open_regular == (can_open && !(feature && zl)));
    assert(out.battle_owns_input ==
           (regular_active || arm_active || can_open));
    assert(!out.open_arm || (feature && zl && fresh_r));
    if (autoplay || regular_active || arm_active) {
      assert(!out.open_arm && !out.open_regular);
    }
    if (!fresh_r && !regular_active && !arm_active) {
      assert(!out.battle_owns_input);
    }
    ++cases;
  }
  assert(cases==64);
}

void ordinary_r_mode_is_unchanged_without_experimental_flag() {
  const auto direct=select_arm_battle_entry(false,true,false,false,false,false);
  const auto with_zl=select_arm_battle_entry(false,true,true,false,false,false);
  assert(direct.open_regular && !direct.open_arm);
  assert(with_zl.open_regular && !with_zl.open_arm);
  assert(direct.battle_owns_input && with_zl.battle_owns_input);
}

void zl_r_only_opens_arm_when_explicitly_compiled_and_manually_active() {
  const auto optin=select_arm_battle_entry(true,true,true,false,false,false);
  assert(optin.open_arm && !optin.open_regular && optin.battle_owns_input);
  assert(!select_arm_battle_entry(true,true,true,true,false,false).open_arm);
  assert(!select_arm_battle_entry(true,false,true,false,false,false).open_arm);
  assert(!select_arm_battle_entry(true,true,false,false,false,false).open_arm);
  assert(select_arm_battle_entry(true,true,false,false,false,false).open_regular);
}

void existing_battles_lock_ordinary_and_arm_entry() {
  for(bool feature : {false,true}) {
    for(bool zl : {false,true}) {
      const auto regular=select_arm_battle_entry(
          feature,true,zl,false,true,false);
      const auto experimental=select_arm_battle_entry(
          feature,true,zl,false,false,true);
      const auto both=select_arm_battle_entry(
          feature,true,zl,false,true,true);
      for(const auto& route : {regular,experimental,both}) {
        assert(route.battle_owns_input);
        assert(!route.open_regular && !route.open_arm);
      }
    }
  }
}

void arm_release_and_return_reopen_ordinary_r() {
  const auto old=select_arm_battle_entry(true,true,true,false,false,true);
  assert(old.battle_owns_input && !old.open_arm && !old.open_regular);
  const auto after_b=select_arm_battle_entry(
      true,false,false,false,false,false);
  assert(!after_b.open_arm && !after_b.open_regular &&
         !after_b.battle_owns_input);
  const auto reopened=select_arm_battle_entry(
      true,true,false,false,false,false);
  assert(reopened.open_regular && !reopened.open_arm);
}
}

int main() {
  complete_truth_table_six_input_flags();
  ordinary_r_mode_is_unchanged_without_experimental_flag();
  zl_r_only_opens_arm_when_explicitly_compiled_and_manually_active();
  existing_battles_lock_ordinary_and_arm_entry();
  arm_release_and_return_reopen_ordinary_r();
}
