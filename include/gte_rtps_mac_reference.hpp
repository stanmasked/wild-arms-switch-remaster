#pragma once
#include "gte_mac_stage.hpp"
#include "gte_screen_stage.hpp"
#include "gte_transform.hpp"
#include <array>
#include <cstdint>

namespace wa::gte {
// Experimental integration of 4.12 matrix MAC, IR saturation, UNR and screen.
// This is NOT bit-exact GTE. In particular it does not wrap the 44-bit MAC at
// each individual multiply-add or implement the hardware's special IR3 rules.
struct RtpsMacReferenceResult {
    std::array<std::int64_t, 3> raw_mac{};
    MacIrStage mac_ir{};
    std::uint16_t sz3 = 0;
    UnrDivisionResult ratio{};
    ScreenStageResult screen{};
    std::uint32_t flag = 0;
    std::uint32_t returned_sz3_shift2 = 0;
};
constexpr RtpsMacReferenceResult rtps_mac_reference(
        const Transform& transform, Vector3 v, std::uint16_t h,
        std::int32_t ofx_q16, std::int32_t ofy_q16) noexcept {
    RtpsMacReferenceResult out{};
    const std::array<std::int16_t, 3> xyz{v.x, v.y, v.z};
    for (std::size_t i = 0; i < 3; ++i) {
        std::int64_t total = std::int64_t(transform.translation[i]) * 4096;
        for (std::size_t j = 0; j < 3; ++j)
            total += std::int64_t(transform.rotation[i][j]) * xyz[j];
        out.raw_mac[i] = total;
    }
    out.mac_ir = mac_ir_from_raw(out.raw_mac);
    // Depth is derived separately from the pre-clamp third accumulator.
    const auto depth = floor_shift12(out.raw_mac[2]);
    out.sz3 = clamp_sz(depth);
    out.ratio = gte_unr_divide(h, out.sz3);
    out.screen = screen_stage_unr(
        static_cast<std::int16_t>(out.mac_ir.ir[0]),
        static_cast<std::int16_t>(out.mac_ir.ir[1]),
        ofx_q16, ofy_q16, out.ratio);
    out.flag = out.mac_ir.flag | out.screen.flag;
    if (depth < 0 || depth > 65535) out.flag |= (1u << 18);
    if (out.flag & 0x7f87e000u) out.flag |= (1u << 31);
    out.returned_sz3_shift2 = out.sz3 >> 2;
    return out;
}
} // namespace wa::gte
