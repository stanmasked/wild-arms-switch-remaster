#pragma once
#include "gte_rtps_mac44_depth_reference.hpp"
#include "gte_depth_cue_stage.hpp"
namespace wa::gte {
struct RtpsIr0ReferenceResult {
 RtpsMac44DepthResult base{};
 DepthCueStage cue{};
 std::uint32_t flag=0;
};
constexpr RtpsIr0ReferenceResult rtps_ir0_reference(const Transform& transform,Vector3 vertex,std::uint16_t h,std::int32_t ofx,std::int32_t ofy,std::int16_t dqa,std::int32_t dqb,bool sf=true,bool lm=false) noexcept {
 RtpsIr0ReferenceResult out{};
 out.base=rtps_mac44_depth_reference(transform,vertex,h,ofx,ofy,sf,lm);
 out.cue=depth_cue_stage(out.base.ratio.quotient,dqa,dqb);
 out.flag=out.base.flag|out.cue.flags;
 return out;
}
}
