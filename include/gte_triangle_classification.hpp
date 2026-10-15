#pragma once
#include "gte_rtpt_nclip_reference.hpp"
#include <cstdint>

namespace wa::gte {
// The game's polygon winding convention must be established from real assets.
// NCLIP supplies oriented twice-area but no universal front-facing sign.
enum class FrontFace : std::uint8_t { PositiveArea, NegativeArea };
enum class TriangleClass : std::uint8_t {
    FrontFacing, BackFacing, Degenerate, IndeterminateOverflow
};
struct TriangleClassification {
    TriangleClass kind = TriangleClass::Degenerate;
    bool safe_to_cull = false;
};
constexpr TriangleClassification classify_nclip(
    NclipReferenceResult result, FrontFace front) noexcept {
    // The wrapped MAC0 sign is unsafe on an intermediate overflow.
    if (result.flag & ((1u << 15) | (1u << 16)))
        return {TriangleClass::IndeterminateOverflow, false};
    if (result.mac0 == 0) return {TriangleClass::Degenerate, false};
    const bool is_front = (result.mac0 > 0) == (front == FrontFace::PositiveArea);
    return {is_front ? TriangleClass::FrontFacing : TriangleClass::BackFacing,
            !is_front};
}
struct RtptTriangleResult {
    RtptNclipReferenceResult geometry{};
    TriangleClassification facing{};
};
constexpr RtptTriangleResult rtpt_classify_triangle(
    RtpsFifoState prior, const Transform& transform,
    const std::array<Vector3,3>& vertices, std::uint16_t h,
    std::int32_t ofx, std::int32_t ofy, std::int16_t dqa, std::int32_t dqb,
    FrontFace front, bool sf=true, bool lm=false) noexcept {
    RtptTriangleResult result{};
    result.geometry = rtpt_nclip_reference(prior, transform, vertices,
        h, ofx, ofy, dqa, dqb, sf, lm);
    result.facing = classify_nclip(result.geometry.nclip, front);
    return result;
}
} // namespace wa::gte
