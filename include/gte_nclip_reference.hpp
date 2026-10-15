#pragma once
#include "gte_screen_stage.hpp"
#include <array>
#include <cstdint>
#include <limits>

namespace wa::gte {
// Oriented twice-area in screen space. MAC0 stores the low signed 32 bits.
// MAC0 overflow sets FLAG 16/15, which alone do not contribute to FLAG[31].
struct NclipReferenceResult {
    std::int64_t full_area = 0;
    std::int32_t mac0 = 0;
    std::uint32_t flag = 0;
};
constexpr std::int16_t nclip_x(std::uint32_t sxy) noexcept {
    const auto bits = static_cast<std::uint16_t>(sxy);
    return bits < 0x8000u ? static_cast<std::int16_t>(bits)
                          : static_cast<std::int16_t>(static_cast<std::int32_t>(bits)-65536);
}
constexpr std::int16_t nclip_y(std::uint32_t sxy) noexcept {
    const auto bits = static_cast<std::uint16_t>(sxy >> 16);
    return bits < 0x8000u ? static_cast<std::int16_t>(bits)
                          : static_cast<std::int16_t>(static_cast<std::int32_t>(bits)-65536);
}
constexpr NclipReferenceResult nclip_reference(const std::array<std::uint32_t,3>& sxy) noexcept {
    const std::int64_t x0=nclip_x(sxy[0]), y0=nclip_y(sxy[0]);
    const std::int64_t x1=nclip_x(sxy[1]), y1=nclip_y(sxy[1]);
    const std::int64_t x2=nclip_x(sxy[2]), y2=nclip_y(sxy[2]);
    NclipReferenceResult out{};
    out.full_area = x0*(y1-y2)+x1*(y2-y0)+x2*(y0-y1);
    if (out.full_area > std::numeric_limits<std::int32_t>::max()) out.flag |= 1u<<16;
    if (out.full_area < std::numeric_limits<std::int32_t>::min()) out.flag |= 1u<<15;
    out.mac0 = wrap_i32(out.full_area);
    return out;
}
} // namespace wa::gte
