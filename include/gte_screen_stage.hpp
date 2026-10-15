#pragma once
#include "gte_math.hpp"
#include "gte_unr_division.hpp"
#include <cstdint>
#include <limits>

namespace wa::gte {
// GTE screen-coordinate stage using 16.16 OFX/OFY and a Q16 UNR quotient.
// Mirrors MAC0 signed-32-bit wrap and SX/SY saturation, but is not a full RTPS.
struct ScreenStageResult {
    std::int16_t sx = 0;
    std::int16_t sy = 0;
    std::uint32_t sxy = 0;
    std::uint32_t flag = 0;
    std::int32_t mac0_after_y = 0;
};
constexpr std::int64_t floor_shift16(std::int64_t n) noexcept {
    const auto q = n / 65536;
    return q - (n % 65536 < 0 ? 1 : 0);
}
constexpr std::int32_t wrap_i32(std::int64_t n) noexcept {
    const auto bits = static_cast<std::uint32_t>(n);
    return bits <= 0x7fffffffu ? static_cast<std::int32_t>(bits)
        : static_cast<std::int32_t>(static_cast<std::int64_t>(bits) - 4294967296ll);
}
constexpr ScreenStageResult screen_stage_unr(std::int16_t ir1, std::int16_t ir2,
        std::int32_t ofx_q16, std::int32_t ofy_q16, UnrDivisionResult q) noexcept {
    ScreenStageResult result{};
    if (q.divide_overflow) result.flag |= 1u << 17;
    const auto stage = [](std::int16_t ir, std::int32_t of, std::uint32_t quotient,
                           std::uint32_t& flags, bool x) constexpr -> std::int16_t {
        const std::int64_t raw = std::int64_t(of) + std::int64_t(ir) * quotient;
        if (raw > std::numeric_limits<std::int32_t>::max()) flags |= 1u << 16;
        if (raw < std::numeric_limits<std::int32_t>::min()) flags |= 1u << 15;
        // The screen limiter sees the full MAC0 intermediate; only the
        // architectural MAC0 register is truncated to 32 bits.
        const auto pixel = floor_shift16(raw);
        const auto limited = x ? clamp_sx(pixel) : clamp_sy(pixel);
        if (pixel != limited) flags |= 1u << (x ? 14 : 13);
        return limited;
    };
    result.sx = stage(ir1, ofx_q16, q.quotient, result.flag, true);
    result.sy = stage(ir2, ofy_q16, q.quotient, result.flag, false);
    result.sxy = pack_sxy(result.sx, result.sy);
    const std::int64_t raw_y = std::int64_t(ofy_q16) + std::int64_t(ir2)*q.quotient;
    result.mac0_after_y = wrap_i32(raw_y);
    // FLAG summary covers bits 30..23 and 18..13, but not MAC0 bits 16/15 alone.
    if (result.flag & ((1u<<17)|(1u<<14)|(1u<<13))) result.flag |= 1u << 31;
    return result;
}
} // namespace wa::gte
