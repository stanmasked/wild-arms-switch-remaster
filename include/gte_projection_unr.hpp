#pragma once
#include "gte_projection.hpp"
#include "gte_unr_division.hpp"
#include <cstdint>

namespace wa::gte {
// Host comparison path: GTE UNR divide + legacy integer-pixel screen stage.
// NOT an accurate GTE RTPS: OFX/OFY register scaling, MAC widths and FLAG
// aggregation are not modeled. Keep this distinct from project_reference.
struct UnrProjectedPoint {
    ProjectedPoint point{};
    std::uint32_t quotient_q16 = 0;
    bool divide_overflow = false;
};
constexpr UnrProjectedPoint project_unr_reference(std::int32_t x,
        std::int32_t y, std::int64_t z, ProjectionParameters params) noexcept {
    UnrProjectedPoint out{};
    out.point.zero_or_negative_depth = z <= 0;
    out.point.depth_saturated = z < 0 || z > 65535;
    out.point.sz = clamp_sz(z);
    const auto division = gte_unr_divide(params.h, out.point.sz);
    out.quotient_q16 = division.quotient;
    out.divide_overflow = division.divide_overflow;
    out.point.ratio_saturated = division.divide_overflow;
    const std::int64_t px = static_cast<std::int64_t>(params.ofx)
        + (static_cast<std::int64_t>(x) * division.quotient) / 65536;
    const std::int64_t py = static_cast<std::int64_t>(params.ofy)
        + (static_cast<std::int64_t>(y) * division.quotient) / 65536;
    out.point.sx = clamp_sx(px);
    out.point.sy = clamp_sy(py);
    out.point.x_saturated = px != out.point.sx;
    out.point.y_saturated = py != out.point.sy;
    out.point.sxy = pack_sxy(out.point.sx, out.point.sy);
    return out;
}
} // namespace wa::gte
