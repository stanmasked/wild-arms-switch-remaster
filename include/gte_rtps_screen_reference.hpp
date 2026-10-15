#pragma once
#include "gte_transform.hpp"
#include "gte_screen_stage.hpp"
#include <cstdint>

namespace wa::gte {
// Host-side composite with GTE-style OFX/OFY (signed 16.16).
// Deliberately distinct from rtps_unr_reference(): still no accurate
// MAC1..MAC3 overflow, SZ FIFO, IR0 computation or complete GTE FLAG.
struct RtpsScreenReferenceResult {
    Transformed transformed{};
    std::uint16_t sz3 = 0;
    UnrDivisionResult ratio{};
    ScreenStageResult screen{};
    std::uint32_t returned_sz3_shift2 = 0;
    bool depth_clamped = false;
};

constexpr RtpsScreenReferenceResult rtps_screen_reference(
        const Transform& transform, Vector3 vertex,
        std::uint16_t h, std::int32_t ofx_q16, std::int32_t ofy_q16) noexcept {
    RtpsScreenReferenceResult out{};
    out.transformed = rotate_translate(transform, vertex, false);
    const auto depth = out.transformed.pre_ir[2];
    out.sz3 = clamp_sz(depth);
    out.depth_clamped = depth < 0 || depth > 65535;
    out.ratio = gte_unr_divide(h, out.sz3);
    out.screen = screen_stage_unr(
        static_cast<std::int16_t>(out.transformed.ir[0]),
        static_cast<std::int16_t>(out.transformed.ir[1]),
        ofx_q16, ofy_q16, out.ratio);
    out.returned_sz3_shift2 = out.sz3 >> 2;
    return out;
}
} // namespace wa::gte
