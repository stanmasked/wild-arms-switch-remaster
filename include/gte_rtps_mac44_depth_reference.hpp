#pragma once
#include "gte_rtps_mac44_reference.hpp"
#include "gte_rtps_depth_stage.hpp"

namespace wa::gte {
struct RtpsMac44DepthResult {
    Matrix44Result matrix{};
    MacIrStage mac_ir{};
    RtpsDepthStage depth{};
    UnrDivisionResult ratio{};
    ScreenStageResult screen{};
    std::uint32_t flag = 0;
    std::uint32_t returned_sz3_shift2 = 0;
};
// Experimental combination; not bit-exact PS1 GTE.
constexpr RtpsMac44DepthResult rtps_mac44_depth_reference(
    const Transform& transform, Vector3 vertex, std::uint16_t h,
    std::int32_t ofx_q16, std::int32_t ofy_q16,
    bool sf = true, bool lm = false) noexcept {
    RtpsMac44DepthResult out{};
    out.matrix = matrix44_accumulate(transform.rotation, transform.translation,
                                    {vertex.x, vertex.y, vertex.z});
    std::array<std::int64_t,3> raw{};
    for (std::size_t i = 0; i < 3; ++i)
        raw[i] = out.matrix.accumulators[i].value;
    out.mac_ir = mac_ir_from_raw(raw, sf, lm);
    out.depth = rtps_depth_stage(out.mac_ir.mac[2], sf, lm);
    out.mac_ir.ir[2] = out.depth.ir3;
    out.mac_ir.flag &= ~(1u << 22);
    out.mac_ir.flag |= out.depth.flags & (1u << 22);
    out.ratio = gte_unr_divide(h, out.depth.sz3);
    out.screen = screen_stage_unr(
        static_cast<std::int16_t>(out.mac_ir.ir[0]),
        static_cast<std::int16_t>(out.mac_ir.ir[1]),
        ofx_q16, ofy_q16, out.ratio);
    out.flag = out.matrix.flag | out.mac_ir.flag | out.depth.flags | out.screen.flag;
    if (out.flag & 0x7f87e000u) out.flag |= 1u << 31;
    out.returned_sz3_shift2 = out.depth.sz3 >> 2;
    return out;
}
} // namespace wa::gte
