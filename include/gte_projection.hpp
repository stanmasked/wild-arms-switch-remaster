#pragma once
#include "gte_math.hpp"
#include <cstdint>
namespace wa::gte {
// Portable host reference, NOT cycle- or bit-accurate PlayStation GTE.
// Inputs/offsets in integer pixels. Perspective ratio is Q16 approximation
// of min(H/Z,2); signed division truncates toward zero.
struct ProjectionParameters {
    std::int32_t ofx = 0, ofy = 0;
    std::uint16_t h = 0;
};
struct ProjectedPoint {
    std::int16_t sx = 0, sy = 0;
    std::uint16_t sz = 0;
    std::uint32_t sxy = 0;
    bool zero_or_negative_depth = false;
    bool depth_saturated = false;
    bool ratio_saturated = false;
    bool x_saturated = false;
    bool y_saturated = false;
};
constexpr ProjectedPoint project_reference(std::int32_t x, std::int32_t y,
                                           std::int64_t z, ProjectionParameters p) noexcept {
    ProjectedPoint out{};
    out.zero_or_negative_depth = z <= 0;
    out.depth_saturated = z < 0 || z > 65535;
    out.sz = clamp_sz(z);
    const std::uint64_t safe_z = out.sz == 0 ? 1 : out.sz;
    const std::uint64_t raw_factor = (std::uint64_t(p.h) * 65536) / safe_z;
    out.ratio_saturated = raw_factor > 131072;
    const std::int64_t factor = static_cast<std::int64_t>(out.ratio_saturated ? 131072 : raw_factor);
    const std::int64_t projected_x = std::int64_t(p.ofx) + (std::int64_t(x)*factor)/65536;
    const std::int64_t projected_y = std::int64_t(p.ofy) + (std::int64_t(y)*factor)/65536;
    out.sx = clamp_sx(projected_x);
    out.sy = clamp_sy(projected_y);
    out.x_saturated = projected_x != out.sx;
    out.y_saturated = projected_y != out.sy;
    out.sxy = pack_sxy(out.sx,out.sy);
    return out;
}
} // namespace wa::gte
