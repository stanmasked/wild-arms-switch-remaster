#pragma once
#include "gte_rtpt_reference.hpp"
#include "gte_nclip_reference.hpp"

namespace wa::gte {
struct RtptNclipReferenceResult {
    RtptReferenceResult rtpt{};
    NclipReferenceResult nclip{};
};
// Sequential RTPT then NCLIP. NCLIP overwrites architectural MAC0 and FLAG;
// it does not OR them with previous RTPT flags.
constexpr RtptNclipReferenceResult rtpt_nclip_reference(
        RtpsFifoState prior, const Transform& transform,
        const std::array<Vector3,3>& vertices, std::uint16_t h,
        std::int32_t ofx, std::int32_t ofy, std::int16_t dqa, std::int32_t dqb,
        bool sf=true, bool lm=false) noexcept {
    RtptNclipReferenceResult out{};
    out.rtpt = rtpt_reference(prior,transform,vertices,h,ofx,ofy,dqa,dqb,sf,lm);
    out.nclip = nclip_reference(out.rtpt.fifo.sxy);
    return out;
}
} // namespace wa::gte
