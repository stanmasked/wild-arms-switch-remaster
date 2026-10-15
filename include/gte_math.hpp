#pragma once
#include <cstdint>
namespace wa::gte {
// Integer building blocks, NOT an emulation of PS1 GTE RTPS.
// Defined results on host compilers, including negative fixed-point values.
constexpr std::int64_t floor_shift12(std::int64_t value) noexcept {
    const auto quotient = value / 4096;
    const auto remainder = value % 4096;
    return quotient - (remainder < 0 ? 1 : 0);
}
constexpr std::int32_t clamp_ir_signed(std::int64_t value) noexcept {
    if (value < -32768) return -32768;
    if (value > 32767) return 32767;
    return static_cast<std::int32_t>(value);
}
constexpr std::int32_t clamp_ir_unsigned(std::int64_t value) noexcept {
    if (value < 0) return 0;
    if (value > 32767) return 32767;
    return static_cast<std::int32_t>(value);
}
constexpr std::uint16_t clamp_sz(std::int64_t value) noexcept {
    if (value <= 0) return 0;
    if (value >= 65535) return 65535;
    return static_cast<std::uint16_t>(value);
}
constexpr std::int16_t clamp_sx(std::int64_t value) noexcept {
    return static_cast<std::int16_t>(value < -1024 ? -1024 : value > 1023 ? 1023 : value);
}
constexpr std::int16_t clamp_sy(std::int64_t value) noexcept {
    return static_cast<std::int16_t>(value < -1024 ? -1024 : value > 1023 ? 1023 : value);
}
constexpr std::uint32_t pack_sxy(std::int16_t x, std::int16_t y) noexcept {
    return std::uint32_t(static_cast<std::uint16_t>(x)) |
           (std::uint32_t(static_cast<std::uint16_t>(y)) << 16);
}
} // namespace wa::gte
