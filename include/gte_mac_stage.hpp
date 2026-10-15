#pragma once
#include <array>
#include <cstdint>
#include "gte_math.hpp"

namespace wa::gte {
// GTE MAC1..3 / IR1..3 reference for already accumulated signed values.
// Positive MAC overflow: > 2^43-1; negative: < -2^43.
// MAC register is the low 32 bits after sf adjustment.
// This standalone stage does not implement RTPS matrix accumulation order.
struct MacIrStage {
    std::array<std::int32_t,3> mac{};
    std::array<std::int32_t,3> ir{};
    std::uint32_t flag = 0;
};
constexpr std::int32_t signed_low32(std::int64_t value) noexcept {
    const auto bits = static_cast<std::uint32_t>(value);
    return bits <= 0x7fffffffu ? static_cast<std::int32_t>(bits)
        : static_cast<std::int32_t>(std::int64_t(bits) - 4294967296LL);
}
constexpr MacIrStage mac_ir_from_raw(std::array<std::int64_t,3> raw,
                                     bool shift12 = true, bool lm = false) noexcept {
    MacIrStage out{};
    constexpr std::int64_t maximum = (std::int64_t{1} << 43) - 1;
    constexpr std::int64_t minimum = -(std::int64_t{1} << 43);
    for (std::size_t i=0; i<3; ++i) {
        const auto wide = raw[i];
        if (wide > maximum) out.flag |= 1u << (30 - i);
        if (wide < minimum) out.flag |= 1u << (27 - i);
        const auto shifted = shift12 ? floor_shift12(wide) : wide;
        out.mac[i] = signed_low32(shifted);
        out.ir[i] = lm ? clamp_ir_unsigned(out.mac[i]) : clamp_ir_signed(out.mac[i]);
        if (out.mac[i] != out.ir[i]) out.flag |= 1u << (24 - i);
    }
    // Bit22 (IR3) alone does not contribute to summary bit31.
    if (out.flag & 0x7f87e000u) out.flag |= 0x80000000u;
    return out;
}
} // namespace wa::gte
