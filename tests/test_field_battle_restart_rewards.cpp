// Stage 362: actual controller win => WABJ file => fresh game session,
// then loss/retreat and restart, no original Wild Arms assets.
#include "field_battle_file.hpp"
#include "field_battle_session.hpp"
#include "field_runtime.hpp"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <unistd.h>

using namespace wa::field;
namespace {
struct Temp {
  char path[64]="/tmp/wa-battle-restart-XXXXXX";
  std::string base;
  Temp(){assert(::mkdtemp(path));base=std::string(path)+"/progress";}
  ~Temp(){
    for (const char* suffix:{".a",".b",".a.tmp",".b.tmp"})
      (void)std::remove((base+suffix).c_str());
    (void)::rmdir(path);
  }
};
struct Display {
  static constexpr int kStride=kRasterWidth+8;
  static constexpr std::uint32_t kSentinel=0xCDEF1234u;
  std::vector<std::uint32_t> data=std::vector<std::uint32_t>(
    static_cast<std::size_t>(kStride)*kRasterHeight+16,kSentinel);
  PixelTarget target{data.data(),kRasterWidth,kRasterHeight,kStride};
  void guards() const{
    for(int y=0;y<kRasterHeight;++y)
      for(int x=kRasterWidth;x<kStride;++x)
        assert(data[static_cast<std::size_t>(y)*kStride+x]==kSentinel);
    for(std::size_t i=static_cast<std::size_t>(kStride)*kRasterHeight;
        i<data.size();++i)assert(data[i]==kSentinel);
  }
};
FieldBattleSessionInput open() {
  FieldBattleSessionInput p{};p.open=true;p.manual_mode=true;return p;
}
FieldBattleSessionInput attack(){
  FieldBattleSessionInput p{};p.pad.confirm=true;return p;
}
FieldBattleSessionInput retreat(){
  FieldBattleSessionInput p{};p.close=true;return p;
}
BattleSceneFrame win_with_real_controller(FieldBattleSession& session,
                                           Display& screen) {
  assert(advance_battle_session(session,open(),screen.target).entered);
  // Shorten the synthetic enemies *only in this test fixture* so two
  // real controller A actions exercise a complete, deterministic win.
  session.battle.enemies[0].hp=1;
  session.battle.enemies[1].hp=1;
  const auto first=advance_battle_session(session,attack(),screen.target);
  assert(first.control.status==BattleControlStatus::ActionApplied);
  assert(first.control.action.inflicted==1);
  assert(advance_battle_session(session,{},screen.target).status==
         BattleSceneStatus::Rendered);
  const auto last=advance_battle_session(session,attack(),screen.target);
  assert(last.control.status==BattleControlStatus::ActionApplied);
  assert(session.battle.phase==BattlePhase::Victory);
  const auto finished=advance_battle_session(session,retreat(),screen.target);
  assert(finished.exited&&finished.resolution==BattleResolution::Victory);
  return finished;
}
void boot_from_disk(const std::string& file,FieldBattleSession& fresh,
                    std::uint64_t expected_generation) {
  BattleProgress recovered{};
  const auto loaded=load_battle_progress_file(file,recovered);
  assert(loaded.status==BattleJournalStatus::Loaded);
  assert(loaded.generation==expected_generation);
  fresh.history=recovered.history;
  fresh.rewards=recovered.rewards;
}
void test_win_restart_retreat_restart_win_without_reward_duplication(){
  Temp files;
  Display view;
  const auto field_world=make_demo_world();
  auto field=start_field_runtime(field_world,19200000ULL,0);
  assert(advance_field_runtime(field_world,field,0,{},view.target).status==
         RuntimeStatus::Rendered);
  const auto original_pixels=view.data;
  FieldBattleSession first_boot{};
  BattleProgress missing{};
  assert(load_battle_progress_file(files.base,missing).status==
         BattleJournalStatus::Missing); // Empty profile, no committed file.

  const auto win=win_with_real_controller(first_boot,view);
  assert(win.payout.experience==kPrototypeVictoryExp);
  assert(win.payout.gella==kPrototypeVictoryGella);
  assert(first_boot.history.victories==1);
  assert(first_boot.rewards.experience==kPrototypeVictoryExp);
  const BattleProgress first_saved{first_boot.history,first_boot.rewards};
  assert(store_battle_progress_file(first_saved,files.base)==
         BattleJournalStatus::Stored);
  const auto a1=read_battle_journal_slot(files.base+".a");
  assert(a1.status==BattleJournalStatus::Loaded&&a1.generation==1);

  // Closing the same fight again is inactive and must not credit again.
  assert(!advance_battle_session(first_boot,retreat(),view.target).exited);
  assert(first_boot.history.victories==1);
  assert(first_boot.rewards.experience==kPrototypeVictoryExp);

  // Simulate a new NRO process by constructing a completely new
  // battle session and loading only from committed WABJ journal files.
  FieldBattleSession second_boot{};
  boot_from_disk(files.base,second_boot,1);
  assert(second_boot.history.victories==1);
  assert(second_boot.history.retreats==0);
  assert(second_boot.history.last==BattleResolution::Victory);
  assert(second_boot.rewards.experience==kPrototypeVictoryExp);
  assert(second_boot.rewards.gella==kPrototypeVictoryGella);
  assert(!second_boot.active);
  assert(advance_battle_session(second_boot,open(),view.target).entered);
  assert(second_boot.battle.enemies[0].hp==14);
  assert(second_boot.battle.enemies[1].hp==17);
  assert(second_boot.rewards.experience==kPrototypeVictoryExp);
  const auto closed=advance_battle_session(second_boot,retreat(),view.target);
  assert(closed.exited&&closed.resolution==BattleResolution::Retreat);
  assert(closed.payout.experience==0&&closed.payout.gella==0);
  assert(store_battle_progress_file(
     {second_boot.history,second_boot.rewards},files.base)==
     BattleJournalStatus::Stored);
  assert(read_battle_journal_slot(files.base+".b").generation==2);
  assert(read_battle_journal_slot(files.base+".a").raw==a1.raw);

  FieldBattleSession third_boot{};
  boot_from_disk(files.base,third_boot,2);
  assert(third_boot.history.victories==1);
  assert(third_boot.history.retreats==1);
  assert(third_boot.history.last==BattleResolution::Retreat);
  assert(third_boot.rewards.experience==kPrototypeVictoryExp);
  const auto another=win_with_real_controller(third_boot,view);
  assert(another.payout.experience==kPrototypeVictoryExp);
  assert(another.payout.gella==kPrototypeVictoryGella);
  assert(third_boot.history.victories==2);
  assert(third_boot.history.retreats==1);
  assert(third_boot.rewards.experience==2*kPrototypeVictoryExp);
  assert(third_boot.rewards.gella==2*kPrototypeVictoryGella);
  assert(store_battle_progress_file(
      {third_boot.history,third_boot.rewards},files.base)==
      BattleJournalStatus::Stored);

  FieldBattleSession fourth_boot{};
  boot_from_disk(files.base,fourth_boot,3);
  assert(fourth_boot.history.victories==2);
  assert(fourth_boot.history.retreats==1);
  assert(fourth_boot.rewards.experience==16);
  assert(fourth_boot.rewards.gella==24);
  assert(fourth_boot.history.last==BattleResolution::Victory);
  assert(!field.quicksave.occupied&&field.discoveries.count==0);
  assert(advance_field_runtime(field_world,field,320000,{},view.target).status==
         RuntimeStatus::Rendered);
  assert(view.data==original_pixels); // All reboots preserve the field.
  view.guards();
}
}
int main(){
  test_win_restart_retreat_restart_win_without_reward_duplication();
}
