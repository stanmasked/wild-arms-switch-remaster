#pragma once
#include "gte_projection.hpp"
#include "gte_transform.hpp"
#include <cstdint>

namespace wa::gte {
// Approximate RTPS-like composition for host testing.
// The projection receives clamped IR3 as depth.
// NOT a bit-accurate PlayStation GTE: no MAC overflow, flags or reciprocal.
struct RtpsReferenceResult {
    Transformed transformed{};
    ProjectedPoint projected{};
    std::int32_t returned_sz3_shift2 = 0;
};
constexpr RtpsReferenceResult rtps_reference(const Transform& transform, Vector3 vertex,
                                            ProjectionParameters projection) noexcept {
    RtpsReferenceResult result{};
    result.transformed = rotate_translate(transform, vertex, false);
    result.projected = project_reference(result.transformed.ir[0],
                                         result.transformed.ir[1],
                                         result.transformed.ir[2], projection);
    // Wild Arms helper uses SRA V0,V0,2 after reading GTE SZ3.
    result.returned_sz3_shift2 = static_cast<std::int32_t>(result.projected.sz >> 2);
    return result;
}
} // namespace wa::gte
