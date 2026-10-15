#include "gte_screen_stage.hpp"
#include "gte_depth_cue_stage.hpp"
#include <cassert>
using namespace wa::gte;
constexpr UnrDivisionResult maxratio{0x1ffffu,false};
// Positive wrap: the truncated low 32 bits would produce an in-range SX,
// but the actual full 64-bit accumulator exceeds the +1023 pixel limit.
constexpr auto positive=screen_stage_unr(32767,0,1048576,0,maxratio);
static_assert(positive.sx==1023);
static_assert((positive.flag & ((1u<<16)|(1u<<14)|(1u<<31))) ==
              ((1u<<16)|(1u<<14)|(1u<<31)));
// Negative wrap: equivalent case for SY, with distinct FLAG bits.
constexpr auto negative=screen_stage_unr(0,-32768,0,-1048576,maxratio);
static_assert(negative.sy==-1024);
static_assert((negative.flag & ((1u<<15)|(1u<<13)|(1u<<31))) ==
              ((1u<<15)|(1u<<13)|(1u<<31)));
// MAC0 register wraps, but IR0 saturation still consumes the 64-bit result.
constexpr auto cue_positive=depth_cue_stage(0x1ffffu,32767,1048576);
static_assert(cue_positive.mac0==wrap_i32(1048576ll+32767ll*0x1ffffu));
static_assert(cue_positive.ir0==4096);
static_assert((cue_positive.flags & ((1u<<16)|(1u<<12)))==
              ((1u<<16)|(1u<<12)));
constexpr auto cue_negative=depth_cue_stage(0x1ffffu,-32768,-1048576);
static_assert(cue_negative.mac0==wrap_i32(-1048576ll-32768ll*0x1ffffu));
static_assert(cue_negative.ir0==0);
static_assert((cue_negative.flags & ((1u<<15)|(1u<<12)))==
              ((1u<<15)|(1u<<12)));
int main(){assert(positive.sx==1023 && negative.sy==-1024);}
