#pragma once
// Stage 340: read-only, asset-free battle preview for 1280x720 RGB(A).
// Not yet wired to the Nintendo Switch field loop or ROM resources.
#include "field_battle_controller.hpp"
#include "field_pixels.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace wa::field {

enum class BattleRenderStatus : std::uint8_t {
  Rendered, InvalidTarget, InvalidBattle, InvalidCursor
};

constexpr std::uint32_t kBattleBackground = rgba(12, 19, 31);
constexpr std::uint32_t kBattlePanel = rgba(31, 45, 66);
constexpr std::uint32_t kBattleInactive = rgba(23, 32, 44);
constexpr std::uint32_t kBattleWhite = rgba(246, 247, 252);
constexpr std::uint32_t kBattleMuted = rgba(116, 134, 159);
constexpr std::uint32_t kBattleBlue = rgba(105, 160, 230);
constexpr std::uint32_t kBattleGold = rgba(245, 183, 66);
constexpr std::uint32_t kBattleGreen = rgba(63, 191, 138);
constexpr std::uint32_t kBattleRed = rgba(201, 67, 76);

// A self-contained 5x7 upper-case pixel alphabet, independent of the
// field-journal font and unchanged by story translations or ROM assets.
[[nodiscard]] inline const std::array<std::uint8_t, 7>&
battle_font(char letter) noexcept {
  static constexpr std::array<std::uint8_t, 7> glyphs[] = {
    {14,17,19,21,25,17,14}, // 0
    {4,12,4,4,4,4,14},       // 1
    {14,17,1,2,4,8,31},     // 2
    {30,1,1,14,1,1,30},     // 3
    {2,6,10,18,31,2,2},    // 4
    {31,16,16,30,1,1,30},  // 5
    {14,16,16,30,17,17,14},// 6
    {31,1,2,4,8,8,8},      // 7
    {14,17,17,14,17,17,14},// 8
    {14,17,17,15,1,1,14},  // 9
    {14,17,17,31,17,17,17},// A
    {30,17,17,30,17,17,30},// B
    {14,17,16,16,16,17,14},// C
    {30,17,17,17,17,17,30},// D
    {31,16,16,30,16,16,31},// E
    {31,16,16,30,16,16,16},// F
    {14,17,16,23,17,17,14},// G
    {17,17,17,31,17,17,17},// H
    {14,4,4,4,4,4,14},      // I
    {7,2,2,2,18,18,12},    // J
    {17,18,20,24,20,18,17},// K
    {16,16,16,16,16,16,31},// L
    {17,27,21,21,17,17,17},// M
    {17,25,21,19,17,17,17},// N
    {14,17,17,17,17,17,14},// O
    {30,17,17,30,16,16,16},// P
    {14,17,17,17,21,18,13},// Q
    {30,17,17,30,20,18,17},// R
    {15,16,16,14,1,1,30}, // S
    {31,4,4,4,4,4,4},      // T
    {17,17,17,17,17,17,14},// U
    {17,17,17,17,17,10,4}, // V
    {17,17,17,21,21,21,10},// W
    {17,17,10,4,10,17,17}, // X
    {17,17,10,4,4,4,4},    // Y
    {31,1,2,4,8,16,31},   // Z
    {0,0,0,0,0,0,0},       // blank (index 36)
    {0,0,0,4,0,0,4},       // colon (index 37)
    {1,1,2,4,8,16,16},    // slash (index 38)
    {0,0,0,31,0,0,0},     // dash (index 39)
  };
  if (letter >= '0' && letter <= '9') return glyphs[letter-'0'];
  if (letter >= 'A' && letter <= 'Z') return glyphs[10+letter-'A'];
  if (letter == ':') return glyphs[37];
  if (letter == '/') return glyphs[38];
  if (letter == '-') return glyphs[39];
  return glyphs[36];
}

inline void battle_text(const PixelTarget& target, int x, int y,
                        const char* message, std::uint32_t ink) noexcept {
  for (std::size_t i=0; message[i]!='\0' && i<64; ++i) {
    const auto& bits=battle_font(message[i]);
    for (int row=0;row<7;++row)
      for (int col=0;col<5;++col)
        if ((bits[static_cast<std::size_t>(row)]>>(4-col))&1u)
          fill_raster_rect(target,x+static_cast<int>(i)*13+col*2,
                           y+row*2,2,2,ink);
  }
}

inline void battle_outline(const PixelTarget& target, int x, int y,
                           int width, int height, std::uint32_t ink) noexcept {
  fill_raster_rect(target,x,y,width,4,ink);
  fill_raster_rect(target,x,y+height-4,width,4,ink);
  fill_raster_rect(target,x,y,4,height,ink);
  fill_raster_rect(target,x+width-4,y,4,height,ink);
}

inline void battle_health(const PixelTarget& target, int x, int y,
                          const BattleFighter& unit,
                          std::uint32_t alive_ink) noexcept {
  constexpr int kBarWidth=340;
  fill_raster_rect(target,x,y,kBarWidth,20,kBattleBackground);
  // uint32_t product is bounded by 65,535*340; max_hp is nonzero.
  const int filled=static_cast<int>(
      (static_cast<std::uint32_t>(unit.hp)*kBarWidth)/unit.max_hp);
  if (filled>0)
    fill_raster_rect(target,x,y,filled,20,alive_ink);
}

// Returns failure before writing even one pixel. No Battle/Cursor
// mutation, heap allocation, texture dependency, or emulator coupling.
[[nodiscard]] inline BattleRenderStatus draw_field_battle(
    const PixelTarget& target, const FieldBattle& battle,
    const BattleCursor& cursor) noexcept {
  if (target.pixels==nullptr || target.width!=kRasterWidth ||
      target.height!=kRasterHeight || target.stride_pixels<kRasterWidth ||
      target.stride_pixels>8192) return BattleRenderStatus::InvalidTarget;
  if (!valid_field_battle(battle)) return BattleRenderStatus::InvalidBattle;
  if (cursor.actor>=kBattlePartySize || cursor.target>=kBattleEnemyCount)
    return BattleRenderStatus::InvalidCursor;

  fill_raster_rect(target,0,0,kRasterWidth,kRasterHeight,kBattleBackground);
  fill_raster_rect(target,0,0,kRasterWidth,76,rgba(28,40,57));
  battle_text(target,70,28,"BATTLE PROTOTYPE",kBattleWhite);
  char line[80]{};
  (void)std::snprintf(line,sizeof(line),"ROUND %u",battle.round);
  battle_text(target,995,28,line,kBattleGold);
  battle_text(target,72,90,"PARTY",kBattleBlue);
  battle_text(target,674,90,"ENEMIES",kBattleGold);

  for (std::size_t i=0;i<kBattlePartySize;++i) {
    const auto& unit=battle.party[i];
    const int x=70, y=120+static_cast<int>(i)*164;
    const bool alive=unit.hp>0;
    fill_raster_rect(target,x,y,540,138,alive?kBattlePanel:kBattleInactive);
    if (battle.phase==BattlePhase::Player && i==cursor.actor && alive)
      battle_outline(target,x,y,540,138,kBattleBlue);
    (void)std::snprintf(line,sizeof(line),"HERO %u",static_cast<unsigned>(i+1));
    battle_text(target,x+22,y+19,line,alive?kBattleWhite:kBattleMuted);
    (void)std::snprintf(line,sizeof(line),"HP %u/%u",
                        static_cast<unsigned>(unit.hp),
                        static_cast<unsigned>(unit.max_hp));
    battle_text(target,x+22,y+49,line,alive?kBattleWhite:kBattleMuted);
    battle_health(target,x+22,y+79,unit,kBattleGreen);
    const char* state=!alive?"DOWN":battle.guarding[i]?"GUARD":
                       battle.acted[i]?"ACTED":"READY";
    battle_text(target,x+22,y+109,state,
                battle.guarding[i]?kBattleBlue:kBattleMuted);
    fill_raster_rect(target,x+440,y+33,56,60,
                     alive?kBattleBlue:kBattleMuted);
    fill_raster_rect(target,x+453,y+46,30,20,rgba(12,19,31));
  }
  for (std::size_t i=0;i<kBattleEnemyCount;++i) {
    const auto& unit=battle.enemies[i];
    const int x=670,y=165+static_cast<int>(i)*242;
    const bool alive=unit.hp>0;
    fill_raster_rect(target,x,y,540,164,alive?kBattlePanel:kBattleInactive);
    if (battle.phase==BattlePhase::Player && i==cursor.target && alive)
      battle_outline(target,x,y,540,164,kBattleGold);
    (void)std::snprintf(line,sizeof(line),"FOE %u",static_cast<unsigned>(i+1));
    battle_text(target,x+22,y+22,line,alive?kBattleWhite:kBattleMuted);
    (void)std::snprintf(line,sizeof(line),"HP %u/%u",
                        static_cast<unsigned>(unit.hp),
                        static_cast<unsigned>(unit.max_hp));
    battle_text(target,x+22,y+52,line,alive?kBattleWhite:kBattleMuted);
    battle_health(target,x+22,y+84,unit,kBattleRed);
    battle_text(target,x+22,y+118,alive?"ACTIVE":"DOWN",kBattleMuted);
    fill_raster_rect(target,x+445,y+35,52,60,
                     alive?kBattleRed:kBattleMuted);
    fill_raster_rect(target,x+456,y+48,30,20,kBattleBackground);
  }
  fill_raster_rect(target,0,617,kRasterWidth,103,rgba(28,40,57));
  battle_text(target,70,648,"A STRIKE  Y GUARD  D PAD SELECT",kBattleWhite);
  if (battle.phase!=BattlePhase::Player) {
    fill_raster_rect(target,320,294,640,106,kBattleBackground);
    battle_outline(target,320,294,640,106,
      battle.phase==BattlePhase::Victory?kBattleGreen:kBattleRed);
    battle_text(target,532,339,
      battle.phase==BattlePhase::Victory?"VICTORY":"DEFEAT",kBattleWhite);
  }
  return BattleRenderStatus::Rendered;
}

} // namespace wa::field
