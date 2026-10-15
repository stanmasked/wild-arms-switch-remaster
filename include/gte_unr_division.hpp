#pragma once
#include <cstdint>

namespace wa::gte {
// PS1 GTE perspective divider, modeled from the published UNR algorithm.
// The overflow flag here specifically indicates the H >= 2*SZ3 case; it
// is not the complete GTE FLAG register.
struct UnrDivisionResult {
    std::uint32_t quotient;
    bool divide_overflow;
};

constexpr std::uint32_t unr_table_entry(std::uint32_t index) noexcept {
    // The hardware table is 257 bytes; this mathematical generator produces
    // those entries for valid indices 0..256.
    const std::uint32_t approximation =
        ((0x40000u / (index + 0x100u)) + 1u) / 2u;
    return approximation > 0x101u ? approximation - 0x101u : 0u;
}

constexpr UnrDivisionResult gte_unr_divide(std::uint16_t h,
                                            std::uint16_t sz3) noexcept {
    if (std::uint32_t(h) >= 2u * std::uint32_t(sz3))
        return {0x1ffffu, true};
    std::uint32_t d = sz3;
    std::uint32_t shift = 0;
    while (d < 0x8000u) {
        d <<= 1;
        ++shift;
    }
    const std::uint32_t n = std::uint32_t(h) << shift;
    const std::uint32_t index = (d - 0x7fc0u) >> 7;
    const std::uint32_t u = unr_table_entry(index) + 0x101u;
    const std::uint32_t d1 = (0x2000080u - d * u) >> 8;
    const std::uint32_t d2 = (0x80u + d1 * u) >> 8;
    const std::uint64_t q = (std::uint64_t(n) * d2 + 0x8000u) >> 16;
    return {static_cast<std::uint32_t>(q > 0x1ffffu ? 0x1ffffu : q), false};
}
} // namespace wa::gte
