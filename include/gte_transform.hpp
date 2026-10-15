#pragma once
#include "gte_math.hpp"
#include <array>
#include <cstdint>

namespace wa::gte {
// Portable rotation/translation reference stage, NOT PS1 GTE RTPS-equivalent.
// Matrix: signed 4.12 fixed point. Translation: integer world coordinates.
struct Vector3 { std::int16_t x, y, z; };
struct Transform {
    std::array<std::array<std::int16_t, 3>, 3> rotation;
    std::array<std::int32_t, 3> translation;
};
struct Transformed {
    std::array<std::int32_t, 3> ir;
    std::array<std::int64_t, 3> pre_ir;
    std::array<bool, 3> clamped;
};
constexpr Transformed rotate_translate(const Transform& transform, Vector3 v,
                                        bool limit_mode = false) noexcept {
    const std::array<std::int16_t, 3> values{v.x, v.y, v.z};
    Transformed out{};
    for (std::size_t row = 0; row < 3; ++row) {
        std::int64_t accumulator = std::int64_t(transform.translation[row]) * 4096;
        for (std::size_t column = 0; column < 3; ++column)
            accumulator += std::int64_t(transform.rotation[row][column]) * values[column];
        const std::int64_t shifted = floor_shift12(accumulator);
        out.pre_ir[row] = shifted;
        out.ir[row] = limit_mode ? clamp_ir_unsigned(shifted) : clamp_ir_signed(shifted);
        out.clamped[row] = shifted != out.ir[row];
    }
    return out;
}
} // namespace wa::gte
