#include "gte_rtps_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto centered = rtps_reference(identity,{100,-50,200},{320,240,100});
static_assert(centered.transformed.ir[0]==100);
static_assert(centered.transformed.ir[1]==-50);
static_assert(centered.transformed.ir[2]==200);
static_assert(centered.projected.sx==370 && centered.projected.sy==215);
static_assert(centered.projected.sz==200);
static_assert(centered.returned_sz3_shift2==50);
static_assert(centered.projected.sxy==pack_sxy(370,215));
constexpr Transform translated{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{20,10,100}}};
constexpr auto shifted=rtps_reference(translated,{100,-50,100},{0,0,100});
static_assert(shifted.projected.sx==60 && shifted.projected.sy==-20);
static_assert(shifted.returned_sz3_shift2==50);
constexpr auto behind=rtps_reference(identity,{0,0,-1},{0,0,100});
static_assert(behind.projected.zero_or_negative_depth);
static_assert(behind.projected.sz==0 && behind.returned_sz3_shift2==0);
constexpr Transform clamped{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{50000,-50000,50000}}};
constexpr auto limits=rtps_reference(clamped,{0,0,0},{0,0,100});
static_assert(limits.transformed.clamped[0] && limits.transformed.clamped[1] && limits.transformed.clamped[2]);
static_assert(limits.transformed.ir[0]==32767 && limits.transformed.ir[1]==-32768);
static_assert(limits.projected.sz==50000 && limits.returned_sz3_shift2==12500);
constexpr Transform depth_translation{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto wide_z=rtps_reference(depth_translation,{1,1,0},{0,0,100});
static_assert(wide_z.transformed.ir[2]==32767);
static_assert(wide_z.transformed.pre_ir[2]==50000);
static_assert(wide_z.projected.sz==50000);
static_assert(wide_z.returned_sz3_shift2==12500);
int main(){assert(centered.projected.sxy==pack_sxy(370,215));}
