#pragma once
// Stage370: explicit, read-only warning for two invalid progress-journal slots.
// Only rendered while the player chooses the ZL history overlay.
#include "field_battle_file.hpp"
#include "field_battle_view.hpp"

namespace wa::field {

// Do not confuse a genuinely missing first-run journal, a single valid
// fallback, or inaccessible SD storage with two CRC-invalid committed slots.
[[nodiscard]] constexpr bool progress_journal_needs_warning(
    BattleJournalStatus status) noexcept {
  return status == BattleJournalStatus::Corrupt;
}

constexpr int kBattleSaveWarningX = 690;
constexpr int kBattleSaveWarningY = 554;
constexpr int kBattleSaveWarningW = 550;
constexpr int kBattleSaveWarningH = 55;

// No acknowledgment action, state mutation or SD write. The warning is
// deliberately above the preexisting result/reward panel (starts y=612).
// The normal exploration framebuffer remains pixel-exact when ZL is idle.
[[nodiscard]] inline bool draw_progress_journal_warning(
    const PixelTarget& target, bool invalid_both_slots) noexcept {
  if (!invalid_both_slots) return false;
  if (target.pixels == nullptr || target.width != kRasterWidth ||
      target.height != kRasterHeight || target.stride_pixels < kRasterWidth ||
      target.stride_pixels > 8192) return false;

  fill_raster_rect(target, kBattleSaveWarningX, kBattleSaveWarningY,
                   kBattleSaveWarningW, kBattleSaveWarningH, kBattlePanel);
  battle_outline(target, kBattleSaveWarningX, kBattleSaveWarningY,
                 kBattleSaveWarningW, kBattleSaveWarningH, kBattleRed);
  battle_text(target, kBattleSaveWarningX + 21, kBattleSaveWarningY + 11,
              "SAVE JOURNAL INVALID", kBattleWhite);
  battle_text(target, kBattleSaveWarningX + 21, kBattleSaveWarningY + 31,
              "NO AUTOSAVE - KEEP FILES", kBattleRed);
  return true;
}

}  // namespace wa::field
