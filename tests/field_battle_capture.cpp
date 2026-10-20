// Host-only reference frames for the synthetic 1280x720 battle UI.
// These are renderer outputs, NOT Switch/NeXium or original PS1 captures.
#include "field_battle_view.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

using namespace wa::field;

int save_ppm(const std::string& path, const FieldBattle& battle,
             const BattleCursor& cursor) {
  std::vector<std::uint32_t> framebuffer(
      static_cast<std::size_t>(kRasterWidth)*kRasterHeight);
  PixelTarget target{framebuffer.data(),kRasterWidth,kRasterHeight,kRasterWidth};
  if (draw_field_battle(target,battle,cursor)!=BattleRenderStatus::Rendered)
    return 2;
  std::FILE* file=std::fopen(path.c_str(),"wb");
  if (!file) return 3;
  if (std::fprintf(file,"P6\n%d %d\n255\n",kRasterWidth,kRasterHeight)<0) {
    std::fclose(file);
    return 4;
  }
  std::array<unsigned char,kRasterWidth*3> row{};
  bool success=true;
  for (int y=0;y<kRasterHeight;++y) {
    for (int x=0;x<kRasterWidth;++x) {
      const auto pixel=framebuffer[static_cast<std::size_t>(y)*kRasterWidth+x];
      row[static_cast<std::size_t>(x)*3]=static_cast<unsigned char>(pixel&255u);
      row[static_cast<std::size_t>(x)*3+1]=
          static_cast<unsigned char>((pixel>>8)&255u);
      row[static_cast<std::size_t>(x)*3+2]=
          static_cast<unsigned char>((pixel>>16)&255u);
    }
    if (std::fwrite(row.data(),1,row.size(),file)!=row.size()) {
      success=false;
      break;
    }
  }
  if (std::fclose(file)!=0) success=false;
  return success?0:5;
}

int main(int argc,char** argv) {
  if(argc!=2) return 1;
  const std::string prefix=argv[1];
  FieldBattle battle=make_demo_battle();
  BattleCursor cursor{};
  if (int status=save_ppm(prefix+"-initial.ppm",battle,cursor))
    return status;
  // After exactly one A strike, the cursor advances to HERO 2 and FOE 1
  // has 8/14 HP. NeXium will compare the guest frame against these bytes.
  FieldBattle after_strike=battle;
  BattleCursor strike_cursor{};
  const BattleUpdate strike=advance_field_battle(
      after_strike,0,BattleMove::Strike,0);
  if (strike.step!=BattleStep::Applied || strike.inflicted!=6)
    return 9;
  strike_cursor.actor=1;
  if (int status=save_ppm(prefix+"-strike.ppm",after_strike,strike_cursor))
    return status;
  if (advance_field_battle(battle,0,BattleMove::Guard).step!=BattleStep::Applied)
    return 6;
  cursor.actor=1;
  cursor.target=1;
  if (int status=save_ppm(prefix+"-active.ppm",battle,cursor))
    return status;
  battle=make_demo_battle();
  battle.enemies[0].hp=1;
  battle.enemies[1].hp=1;
  cursor={};
  if (advance_field_battle(battle,0,BattleMove::Strike,0).step!=BattleStep::Applied)
    return 7;
  if (advance_field_battle(battle,1,BattleMove::Strike,1).phase!=BattlePhase::Victory)
    return 8;
  return save_ppm(prefix+"-victory.ppm",battle,cursor);
}
