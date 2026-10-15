#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace wa::gte {
// Isolated signed 44-bit per-add accumulator. Model to be compared to real GTE.
// Inputs are signed 64-bit; accumulated sums in this interface must fit int64_t.
struct Mac44Accumulator {
    std::int64_t value = 0; // Sign-extended 44-bit value
    bool positive_overflow = false;
    bool negative_overflow = false;
};
constexpr std::int64_t wrap_signed44(std::int64_t value) noexcept {
    constexpr std::uint64_t mask = (std::uint64_t{1} << 44) - 1;
    constexpr std::uint64_t sign = std::uint64_t{1} << 43;
    const auto bits = static_cast<std::uint64_t>(value) & mask;
    return bits < sign ? static_cast<std::int64_t>(bits)
                       : static_cast<std::int64_t>(bits) - static_cast<std::int64_t>(std::uint64_t{1} << 44);
}
constexpr Mac44Accumulator mac44_add(Mac44Accumulator previous, std::int64_t term) noexcept {
    constexpr std::int64_t maximum = (std::int64_t{1} << 43) - 1;
    constexpr std::int64_t minimum = -(std::int64_t{1} << 43);
    const auto sum = previous.value + term;
    previous.positive_overflow |= sum > maximum;
    previous.negative_overflow |= sum < minimum;
    previous.value = wrap_signed44(sum);
    return previous;
}
struct Matrix44Result {
    std::array<Mac44Accumulator,3> accumulators{};
    std::uint32_t flag = 0;
};
// Translation components are integer world-space units, matrix elements Q12.
constexpr Matrix44Result matrix44_accumulate(
    const std::array<std::array<std::int16_t,3>,3>& matrix,
    const std::array<std::int32_t,3>& translation,
    const std::array<std::int16_t,3>& vertex) noexcept {
    Matrix44Result out{};
    for (std::size_t i=0;i<3;++i) {
        auto acc = mac44_add({}, static_cast<std::int64_t>(translation[i])*4096);
        for (std::size_t j=0;j<3;++j)
            acc = mac44_add(acc,static_cast<std::int64_t>(matrix[i][j])*vertex[j]);
        out.accumulators[i]=acc;
        if(acc.positive_overflow) out.flag |= 1u << (30-i);
        if(acc.negative_overflow) out.flag |= 1u << (27-i);
    }
    if(out.flag & 0x7f87e000u) out.flag |= 1u<<31;
    return out;
}
} // namespace wa::gte
