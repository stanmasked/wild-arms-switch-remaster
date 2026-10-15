#pragma once
#include <cstdint>
namespace wa::gte {
// Partial RTPS IR3/SZ3 saturation model. mac3 is post-sf signed 32-bit MAC3.
// Flag 22 is checked against MAC3 >> 12 when sf=0, regardless of lm.
struct RtpsDepthStage {
    std::int16_t ir3;
    std::uint16_t sz3;
    std::uint32_t flags;
};
constexpr std::int32_t shift12_floor(std::int32_t n) noexcept {
    auto q=n/4096;
    return q - (n%4096 < 0 ? 1 : 0);
}
constexpr RtpsDepthStage rtps_depth_stage(std::int32_t mac3, bool sf, bool lm) noexcept {
    const auto depth=sf ? mac3 : shift12_floor(mac3);
    const auto flag_probe=sf ? mac3 : shift12_floor(mac3);
    std::uint32_t flags=0;
    if(flag_probe < -32768 || flag_probe > 32767) flags|=1u<<22;
    const std::int32_t ir_min=lm?0:-32768;
    const auto ir=mac3<ir_min?ir_min:mac3>32767?32767:mac3;
    if(depth<0 || depth>65535) flags|=(1u<<18)|(1u<<31);
    const auto sz=depth<0?0:depth>65535?65535:depth;
    return {static_cast<std::int16_t>(ir),static_cast<std::uint16_t>(sz),flags};
}
}
