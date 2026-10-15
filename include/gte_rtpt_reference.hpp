#pragma once
#include "gte_rtps_fifo.hpp"
#include <array>
namespace wa::gte {
struct RtptReferenceResult {
 RtpsFifoState fifo{};
 std::array<RtpsIr0ReferenceResult,3> stages{};
 std::uint32_t flag=0;
 std::uint16_t ir0=0;
 std::uint32_t returned_sz3_shift2=0;
};
constexpr RtptReferenceResult rtpt_reference(RtpsFifoState previous,const Transform& transform,const std::array<Vector3,3>& vertices,std::uint16_t h,std::int32_t ofx,std::int32_t ofy,std::int16_t dqa,std::int32_t dqb,bool sf=true,bool lm=false) noexcept {
 RtptReferenceResult out{};
 out.fifo=previous;
 for(std::size_t i=0;i<3;++i){
  const auto stage=rtps_fifo_reference(out.fifo,transform,vertices[i],h,ofx,ofy,dqa,dqb,sf,lm);
  out.fifo=stage.fifo;
  out.stages[i]=stage.rtps;
  out.flag|=stage.rtps.flag;
 }
 out.ir0=out.stages[2].cue.ir0;
 out.returned_sz3_shift2=out.fifo.sz[3]>>2;
 return out;
}
}
