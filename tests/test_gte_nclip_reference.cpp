#include "gte_nclip_reference.hpp"
#include "gte_rtpt_nclip_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr std::array<std::uint32_t,3> ccw{pack_sxy(0,0),pack_sxy(100,0),pack_sxy(0,100)};
constexpr std::array<std::uint32_t,3> cw{pack_sxy(0,0),pack_sxy(0,100),pack_sxy(100,0)};
static_assert(nclip_reference(ccw).mac0==10000);
static_assert(nclip_reference(cw).mac0==-10000);
static_assert(nclip_reference({ccw[0],ccw[0],ccw[2]}).mac0==0);
static_assert(nclip_reference(ccw).flag==0);
constexpr auto positive_overflow=nclip_reference({
    pack_sxy(-32768,-32768),pack_sxy(32767,-32768),pack_sxy(-32768,32767)});
static_assert(positive_overflow.full_area==4294836225ll);
static_assert(positive_overflow.mac0==-131071);
static_assert(positive_overflow.flag==(1u<<16));
constexpr auto negative_overflow=nclip_reference({
    pack_sxy(-32768,-32768),pack_sxy(-32768,32767),pack_sxy(32767,-32768)});
static_assert(negative_overflow.full_area==-4294836225ll);
static_assert(negative_overflow.mac0==131071);
static_assert(negative_overflow.flag==(1u<<15));
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr std::array<Vector3,3> verts{{{0,0,100},{100,0,100},{0,100,100}}};
constexpr auto combined=rtpt_nclip_reference({},identity,verts,100,0,0,0,0);
static_assert(combined.rtpt.fifo.sz==std::array<std::uint16_t,4>{0,100,100,100});
static_assert(combined.nclip.mac0==10000 && combined.nclip.flag==0);
constexpr auto flipped=rtpt_nclip_reference({},identity,
    {{{0,0,100},{0,100,100},{100,0,100}}},100,0,0,0,0);
static_assert(flipped.nclip.mac0==-10000);
constexpr auto flagged=rtpt_nclip_reference({},identity,
    {{{0,0,-1},{100,0,100},{0,100,100}}},100,0,0,0,0);
static_assert((flagged.rtpt.flag&(1u<<18))!=0);
static_assert(flagged.nclip.flag==0);
int main(){assert(combined.nclip.mac0==10000);}
