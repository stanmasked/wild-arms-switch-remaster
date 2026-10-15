#pragma once
#include "gte_mac44_accumulate.hpp"
#include "gte_mac_stage.hpp"
#include "gte_screen_stage.hpp"
#include "gte_transform.hpp"
#include <array>
#include <cstdint>

namespace wa::gte {
// Host comparison route: incremental 44-bit matrix accumulation then MAC/IR,
// UNR and Q16 screen projection. Not hardware-exact RTPS.
struct RtpsMac44Result {
    Matrix44Result matrix{};
    MacIrStage mac_ir{};
    std::uint16_t sz3 = 0;
    UnrDivisionResult ratio{};
    ScreenStageResult screen{};
    std::uint32_t flag = 0;
    std::uint32_t returned_sz3_shift2 = 0;
};
constexpr RtpsMac44Result rtps_mac44_reference(
    const Transform& transform, Vector3 vertex, std::uint16_t h,
    std::int32_t ofx_q16, std::int32_t ofy_q16) noexcept {
    RtpsMac44Result out{};
    out.matrix = matrix44_accumulate(transform.rotation,transform.translation,
                                      {vertex.x,vertex.y,vertex.z});
    std::array<std::int64_t,3> wrapped{};
    for(std::size_t i=0;i<3;++i)
        wrapped[i] = out.matrix.accumulators[i].value;
    out.mac_ir = mac_ir_from_raw(wrapped);
    const auto depth = floor_shift12(wrapped[2]);
    out.sz3 = clamp_sz(depth);
    out.ratio = gte_unr_divide(h,out.sz3);
    out.screen = screen_stage_unr(static_cast<std::int16_t>(out.mac_ir.ir[0]),
                                   static_cast<std::int16_t>(out.mac_ir.ir[1]),
                                   ofx_q16,ofy_q16,out.ratio);
    out.flag = out.matrix.flag | out.mac_ir.flag | out.screen.flag;
    if(depth < 0 || depth > 65535) out.flag |= 1u<<18;
    if(out.flag & 0x7f87e000u) out.flag |= 1u<<31;
    out.returned_sz3_shift2 = out.sz3>>2;
    return out;
}
} // namespace wa::gte
