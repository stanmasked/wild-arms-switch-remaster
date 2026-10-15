#include "gte_rtps_ir0_reference.hpp"
#include <cassert>
#include <cstdint>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto a=rtps_ir0_reference(identity,{100,-50,200},100,320*65536,240*65536,0,0);
static_assert(a.base.screen.sx==370 && a.base.screen.sy==215 && a.flag==0);
static_assert(a.base.returned_sz3_shift2==50 && a.cue.ir0==0);
constexpr auto b=rtps_ir0_reference(identity,{100,-50,200},100,320*65536,240*65536,1,0);
static_assert(b.base.ratio.quotient==0x8000 && b.cue.mac0==32768 && b.cue.ir0==8);
static_assert(a.base.screen.sxy==b.base.screen.sxy);
constexpr auto c=rtps_ir0_reference(identity,{0,0,200},100,0,0,0,4096*4097);
static_assert(c.cue.ir0==4096 && (c.flag&(1u<<12)) && !(c.flag&(1u<<31)));
constexpr auto d=rtps_ir0_reference(identity,{0,0,200},100,0,0,-1,0);
static_assert(d.cue.ir0==0 && (d.flag&(1u<<12)));
constexpr auto e=rtps_ir0_reference(identity,{0,0,200},100,0,0,32767,INT32_MAX);
static_assert((e.cue.flags&(1u<<16)) && !(e.flag&(1u<<31)));
constexpr Transform deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto f=rtps_ir0_reference(deep,{0,0,0},50000,0,0,1,0);
static_assert(f.base.depth.sz3==50000 && f.base.depth.ir3==32767);
static_assert(f.base.returned_sz3_shift2==12500);
int main(){assert(b.cue.ir0==8);}
