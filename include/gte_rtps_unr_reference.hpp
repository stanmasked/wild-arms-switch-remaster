#pragma once
#include "gte_projection_unr.hpp"
#include "gte_transform.hpp"
#include <cstdint>

namespace wa::gte {
// Experimental composite: matrix stage + UNR perspective divider.
// Distinct from the old rtps_reference() for differential comparisons.
// NOT bit-exact hardware RTPS (OFX/OFY, MAC, FLAG and FIFO still simplified).
struct RtpsUnrReferenceResult {
    Transformed transformed{};
    UnrProjectedPoint projected{};
    std::uint32_t returned_sz3_shift2 = 0;
};
constexpr RtpsUnrReferenceResult rtps_unr_reference(
        const Transform& transform, Vector3 vertex,
        ProjectionParameters projection) noexcept {
    RtpsUnrReferenceResult result{};
    result.transformed = rotate_translate(transform, vertex, false);
    result.projected = project_unr_reference(result.transformed.ir[0],
                                            result.transformed.ir[1],
                                            result.transformed.pre_ir[2], projection);
    result.returned_sz3_shift2 = result.projected.point.sz >> 2;
    return result;
}
} // namespace wa::gte
