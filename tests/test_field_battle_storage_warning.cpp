#include "field_battle_storage_warning.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <vector>

namespace {
using namespace wa::field;
void require(bool yes) { if (!yes) std::abort(); }

void test_error_classification() {
  require(progress_journal_needs_warning(BattleJournalStatus::Corrupt));
  for (auto status : {BattleJournalStatus::Missing,
                      BattleJournalStatus::Loaded,
                      BattleJournalStatus::Stored,
                      BattleJournalStatus::IoError,
                      BattleJournalStatus::InvalidProgress,
                      BattleJournalStatus::SequenceExhausted}) {
    require(!progress_journal_needs_warning(status));
  }
  require(kBattleSaveWarningY+kBattleSaveWarningH < 612);
  require(kBattleSaveWarningX+kBattleSaveWarningW <= kRasterWidth);
}

void test_banner_only_on_request_and_bounds() {
  constexpr int stride=kRasterWidth+8;
  constexpr std::uint32_t kGuard=0xD15C0DEu;
  std::vector<std::uint32_t> buffer(
      static_cast<std::size_t>(stride)*kRasterHeight+16, kGuard);
  const PixelTarget target{buffer.data(),kRasterWidth,kRasterHeight,stride};
  const auto at=[&](int x,int y) {
    return buffer[static_cast<std::size_t>(y)*stride+x];
  };
  require(!draw_progress_journal_warning(target,false));
  require(std::all_of(buffer.begin(),buffer.end(),[](auto x) {
    return x==kGuard;
  }));
  require(draw_progress_journal_warning(target,true));
  require(at(kBattleSaveWarningX,kBattleSaveWarningY)==kBattleRed);
  require(at(kBattleSaveWarningX+5,kBattleSaveWarningY+5)==kBattlePanel);
  // The heading now begins with 'S' (0b01111 on its top glyph row):
  // its top-left pixel is background, and the next two pixels are white.
  // The old 'B' heading had ink at the first pixel, so that legacy anchor
  // would incorrectly report a rendering regression after renaming.
  require(at(kBattleSaveWarningX+21,kBattleSaveWarningY+11)==kBattlePanel);
  require(at(kBattleSaveWarningX+23,kBattleSaveWarningY+11)==kBattleWhite);
  require(at(kBattleSaveWarningX+21,kBattleSaveWarningY+31)==kBattleRed);
  require(at(kBattleSaveWarningX+2,kBattleSaveWarningY+
             kBattleSaveWarningH-2)==kBattleRed);
  for (int y=0;y<kRasterHeight;++y) {
    for (int x=0;x<stride;++x) {
      const bool within=x>=kBattleSaveWarningX &&
          x<kBattleSaveWarningX+kBattleSaveWarningW &&
          y>=kBattleSaveWarningY &&
          y<kBattleSaveWarningY+kBattleSaveWarningH;
      if (!within) require(at(x,y)==kGuard);
    }
  }
  for (std::size_t i=static_cast<std::size_t>(stride)*kRasterHeight;
       i<buffer.size();++i) require(buffer[i]==kGuard);
  const PixelTarget invalid{nullptr,kRasterWidth,kRasterHeight,stride};
  require(!draw_progress_journal_warning(invalid,true));
  require(!draw_progress_journal_warning(
      PixelTarget{buffer.data(),kRasterWidth-1,kRasterHeight,stride},true));
  require(!draw_progress_journal_warning(
      PixelTarget{buffer.data(),kRasterWidth,kRasterHeight,kRasterWidth-1},
      true));
}

}  // namespace

int main() {
  test_error_classification();
  test_banner_only_on_request_and_bounds();
}
