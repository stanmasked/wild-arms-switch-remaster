#pragma once
#include "gte_rtps_ir0_reference.hpp"
#include <array>
#include <cstdint>

namespace wa::gte {
// Persistent GTE SZ and SXY FIFOs across consecutive RTPS commands.
// The arithmetic stage remains an experimental host reference.
struct RtpsFifoState {
    std::array<std::uint16_t, 4> sz{};
    std::array<std::uint32_t, 3> sxy{};
};
struct RtpsFifoResult {
    RtpsFifoState fifo{};
    RtpsIr0ReferenceResult rtps{};
};
constexpr RtpsFifoState push_rtps_fifo(RtpsFifoState old,
                                        std::uint16_t sz3,
                                        std::uint32_t sxy2) noexcept {
    old.sz = {old.sz[1], old.sz[2], old.sz[3], sz3};
    old.sxy = {old.sxy[1], old.sxy[2], sxy2};
    return old;
}
constexpr RtpsFifoResult rtps_fifo_reference(
        RtpsFifoState prior, const Transform& transform, Vector3 vertex,
        std::uint16_t h, std::int32_t ofx_q16, std::int32_t ofy_q16,
        std::int16_t dqa, std::int32_t dqb,
        bool sf = true, bool lm = false) noexcept {
    const auto rtps = rtps_ir0_reference(transform, vertex, h, ofx_q16,
                                         ofy_q16, dqa, dqb, sf, lm);
    return {push_rtps_fifo(prior, rtps.base.depth.sz3,
                           rtps.base.screen.sxy), rtps};
}
} // namespace wa::gte
