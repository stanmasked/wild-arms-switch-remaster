#pragma once
#include "gte_screen_stage.hpp"
#include <cstdint>
#include <limits>
namespace wa::gte {
// GTE RTPS depth-cue MAC0/IR0 subset. DQA signed16, DQB signed32,
// divide quotient Q16 from gte_unr_divide(). Not the entire RTPS pipeline.
struct DepthCueStage {
    std::int32_t mac0 = 0;
    std::uint16_t ir0 = 0;
    std::uint32_t flags = 0;
};
constexpr DepthCueStage depth_cue_stage(std::uint32_t quotient_q16,
        std::int16_t dqa, std::int32_t dqb) noexcept {
    DepthCueStage out{};
    const auto raw = std::int64_t(dqa) * quotient_q16 + std::int64_t(dqb);
    if (raw > std::numeric_limits<std::int32_t>::max()) out.flags |= 1u << 16;
    if (raw < std::numeric_limits<std::int32_t>::min()) out.flags |= 1u << 15;
    out.mac0 = wrap_i32(raw);
    // IR0 saturation consumes the full intermediate, not wrapped MAC0.
    const auto shifted = floor_shift12(raw);
    if (shifted < 0 || shifted > 4096) out.flags |= 1u << 12;
    out.ir0 = static_cast<std::uint16_t>(shifted < 0 ? 0 : shifted > 4096 ? 4096 : shifted);
    // FLAG[31] does not include bits 16,15 or 12 by themselves.
    return out;
}
} // namespace wa::gte
