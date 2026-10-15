#include "gte_depth_cue_stage.hpp"
#include <cassert>
#include <cstdint>
using namespace wa::gte;
constexpr auto zero = depth_cue_stage(0x10000,0,0);
static_assert(zero.ir0==0 && zero.flags==0);
constexpr auto positive = depth_cue_stage(0x10000,1,0);
static_assert(positive.mac0==65536 && positive.ir0==16);
constexpr auto only_dqb = depth_cue_stage(0,0,4096);
static_assert(only_dqb.ir0==1);
constexpr auto negative = depth_cue_stage(0x10000,-1,0);
static_assert(negative.ir0==0 && negative.flags==(1u<<12));
constexpr auto max_ir = depth_cue_stage(0,0,4096*4096);
static_assert(max_ir.ir0==4096 && max_ir.flags==0);
constexpr auto saturated = depth_cue_stage(0,0,4096*4096+4096);
static_assert(saturated.ir0==4096 && saturated.flags==(1u<<12));
constexpr auto pos_overflow = depth_cue_stage(0x1ffff,32767,INT32_MAX);
static_assert((pos_overflow.flags & (1u<<16)) != 0);
static_assert((pos_overflow.flags & (1u<<31)) == 0);
constexpr auto neg_overflow = depth_cue_stage(0x1ffff,-32768,INT32_MIN);
static_assert((neg_overflow.flags & (1u<<15)) != 0);
static_assert((neg_overflow.flags & (1u<<31)) == 0);
constexpr auto just_negative = depth_cue_stage(0,0,-1);
static_assert(just_negative.ir0==0 && (just_negative.flags&(1u<<12)));
int main(){assert(positive.ir0==16);}
