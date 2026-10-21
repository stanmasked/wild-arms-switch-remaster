#include "field_private_icon.hpp"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace {
using namespace wa::field;

void put16(std::uint8_t* p, std::uint16_t value) {
  p[0] = static_cast<std::uint8_t>(value);
  p[1] = static_cast<std::uint8_t>(value >> 8);
}
void put32(std::uint8_t* p, std::uint32_t value) {
  for (int j = 0; j < 4; ++j)
    p[j] = static_cast<std::uint8_t>(value >> (8 * j));
}
std::vector<std::uint8_t> make_test_file() {
  std::vector<std::uint8_t> bytes(kPrivateIconFileBytes, 0);
  bytes[0] = 'W'; bytes[1] = 'A';
  bytes[2] = 'I'; bytes[3] = 'C';
  put32(bytes.data() + 4, 1);
  put16(bytes.data() + 8, 256);
  put16(bytes.data() + 10, 256);
  put16(bytes.data() + 12, 16);
  put16(bytes.data() + 14, 0);
  put32(bytes.data() + 16,
        static_cast<std::uint32_t>(kPrivateIconPaletteBytes +
                                   kPrivateIconPixels));
  for (int index = 0; index < 16; ++index) {
    const auto color = rgba(static_cast<unsigned>(index * 15), 0u,
                            static_cast<unsigned>(255 - index * 15));
    put32(bytes.data() + kPrivateIconHeaderBytes + 4 * index, color);
  }
  auto* pixels = bytes.data() + kPrivateIconHeaderBytes +
                 kPrivateIconPaletteBytes;
  for (std::size_t i = 0; i < kPrivateIconPixels; ++i)
    pixels[i] = static_cast<std::uint8_t>(i % 16);
  put32(bytes.data() + 20, private_icon_crc32(
      bytes.data() + kPrivateIconHeaderBytes,
      kPrivateIconPaletteBytes + kPrivateIconPixels));
  return bytes;
}
void fix_crc(std::vector<std::uint8_t>& bytes) {
  put32(bytes.data() + 20, private_icon_crc32(
      bytes.data() + kPrivateIconHeaderBytes,
      kPrivateIconPaletteBytes + kPrivateIconPixels));
}
}

int main() {
  using namespace wa::field;
  const auto original = make_test_file();
  PrivateIcon icon{};
  assert(decode_private_icon(original.data(), original.size(), icon));
  assert(icon.valid);
  assert(icon.indices[0] == 0 && icon.indices[17] == 1);
  assert(icon.palette[15] == rgba(225,0,30));

  // Fit exact 256x256 texture at x=12,y=8 into a stride-padded buffer.
  constexpr int width = 300, height = 290, stride = 320;
  constexpr std::uint32_t untouched = 0x12345678;
  std::vector<std::uint32_t> screen(stride * height, untouched);
  const PixelTarget target{screen.data(), width, height, stride};
  assert(draw_private_icon(icon, target, 12, 8));
  assert(screen[8 * stride + 12] == icon.palette[0]);
  assert(screen[8 * stride + 13] == icon.palette[1]);
  assert(screen[(8 + 255) * stride + 12] == icon.palette[0]);
  assert(screen[8 * stride + 11] == untouched);
  assert(screen[0] == untouched);
  assert(screen[8 * stride + 299] == untouched);

  auto invalid_draw = [&](int x, int y, PixelTarget dst) {
    std::fill(screen.begin(), screen.end(), untouched);
    assert(!draw_private_icon(icon, dst, x, y));
    assert(std::all_of(screen.begin(), screen.end(),
                       [](std::uint32_t px){return px == untouched;}));
  };
  invalid_draw(-1, 8, target);
  invalid_draw(12, -1, target);
  invalid_draw(45, 8, target);
  invalid_draw(12, 35, target);
  invalid_draw(12, 8, PixelTarget{screen.data(),width,height,width-1});
  invalid_draw(12, 8, PixelTarget{nullptr,width,height,stride});

  // Every invalid file clears a previously valid preview.
  auto reject = [&](std::vector<std::uint8_t> candidate) {
    icon.valid = true;
    assert(!decode_private_icon(candidate.data(), candidate.size(), icon));
    assert(!icon.valid);
  };
  {
    auto bytes = original;
    bytes[0] = '!';
    reject(bytes);
  }
  {
    auto bytes = original;
    put32(bytes.data() + 4, 2);
    reject(bytes);
  }
  {
    auto bytes = original;
    put16(bytes.data() + 8, 255);
    reject(bytes);
  }
  {
    auto bytes = original;
    put16(bytes.data() + 14, 1);
    reject(bytes);
  }
  {
    auto bytes = original;
    bytes.back() ^= 1;
    reject(bytes); // CRC mismatch
  }
  {
    auto bytes = original;
    bytes[kPrivateIconHeaderBytes + 3] = 127;
    fix_crc(bytes);
    reject(bytes); // non-opaque palette explicitly unsupported
  }
  {
    auto bytes = original;
    bytes[kPrivateIconHeaderBytes + kPrivateIconPaletteBytes] = 16;
    fix_crc(bytes);
    reject(bytes); // out-of-range index even with matching CRC
  }
  {
    auto bytes = original;
    bytes.push_back(0);
    reject(bytes);
  }
  {
    auto bytes = original;
    bytes.pop_back();
    reject(bytes);
  }
  assert(!decode_private_icon(nullptr, kPrivateIconFileBytes, icon));
  assert(!load_private_icon_file(nullptr, icon));
  assert(!load_private_icon_file(
      "path-does-not-exist-private-icon-test.waic", icon));
  return 0;
}
