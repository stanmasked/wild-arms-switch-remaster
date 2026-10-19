#include "field_save_feedback.hpp"

#include <algorithm>
#include <cstdlib>
#include <cstdint>
#include <vector>

namespace {
using namespace wa::field;
void expect(bool v) { if (!v) std::abort(); }

void test_feedback_codes_and_lifecycle() {
  StorageFeedback feedback{};
  expect(feedback.notice == StorageNotice::None &&
         feedback.remaining_ms == 0);
  begin_storage_notice(feedback, StorageNotice::SdSaved);
  expect(feedback.remaining_ms == 900 &&
         feedback.notice == StorageNotice::SdSaved);
  advance_storage_notice(feedback, 100);
  expect(feedback.remaining_ms == 800);
  begin_storage_notice(feedback, StorageNotice::RamOnly);
  expect(feedback.remaining_ms == 900 &&
         feedback.notice == StorageNotice::RamOnly);
  advance_storage_notice(feedback, 899);
  expect(feedback.notice == StorageNotice::RamOnly &&
         feedback.remaining_ms == 1);
  advance_storage_notice(feedback, 1);
  expect(feedback.notice == StorageNotice::None &&
         feedback.remaining_ms == 0);
  advance_storage_notice(feedback, 50000);
  expect(feedback.remaining_ms == 0);
  begin_storage_notice(feedback, StorageNotice::BadSave);
  begin_storage_notice(feedback, StorageNotice::None);
  expect(feedback.notice == StorageNotice::None &&
         feedback.remaining_ms == 0);

  constexpr StorageNotice all[]{
    StorageNotice::SdSaved, StorageNotice::RamOnly,
    StorageNotice::SdLoaded, StorageNotice::RamLoaded,
    StorageNotice::SdError, StorageNotice::BadSave, StorageNotice::NoSave};
  for (const auto notice : all) {
    expect(storage_notice_label(notice)[0] != '\0');
    expect(storage_notice_color(notice) != rgba(0,0,0));
  }
}

void test_onscreen_messages_only_touch_status_corner() {
  constexpr int stride = kRasterWidth + 8;
  std::vector<std::uint32_t> pixels(
      static_cast<std::size_t>(stride) * kRasterHeight + 16,
      0xBADC0DEu);
  PixelTarget surface{pixels.data(), kRasterWidth,kRasterHeight,stride};
  const auto at = [&](int x,int y) {
    return pixels[static_cast<std::size_t>(y) * stride + x];
  };
  StorageFeedback feedback{};
  expect(!draw_storage_notice(surface,feedback));
  expect(std::all_of(pixels.begin(), pixels.end(), [](auto x) {
    return x == 0xBADC0DEu;
  }));
  for (const auto code : {StorageNotice::SdSaved,StorageNotice::RamOnly,
                          StorageNotice::SdLoaded,StorageNotice::RamLoaded,
                          StorageNotice::SdError,StorageNotice::BadSave,
                          StorageNotice::NoSave}) {
    begin_storage_notice(feedback,code);
    expect(draw_storage_notice(surface,feedback));
    expect(at(kStorageNoticeX,kStorageNoticeY) ==
           storage_notice_color(code));
    expect(at(kStorageNoticeX+15,kStorageNoticeY+17) ==
           storage_notice_color(code));
    expect(at(kStorageNoticeX+50,kStorageNoticeY+17) ==
           rgba(17,26,40));
    expect(at(kStorageNoticeX+52,kStorageNoticeY+17) != 0xBADC0DEu);
    expect(at(0,0)==0xBADC0DEu && at(900,200)==0xBADC0DEu &&
           at(kRasterWidth-1,kRasterHeight-1)==0xBADC0DEu);
    for (int y=0;y<kRasterHeight;++y)
      for (int x=kRasterWidth;x<stride;++x)
        expect(at(x,y)==0xBADC0DEu);
  }
  advance_storage_notice(feedback,kStorageNoticeDurationMs);
  expect(!draw_storage_notice(surface,feedback));
  PixelTarget bad{nullptr,kRasterWidth,kRasterHeight,stride};
  begin_storage_notice(feedback,StorageNotice::SdSaved);
  expect(!draw_storage_notice(bad,feedback));
}

} // namespace
int main() {
  test_feedback_codes_and_lifecycle();
  test_onscreen_messages_only_touch_status_corner();
}
