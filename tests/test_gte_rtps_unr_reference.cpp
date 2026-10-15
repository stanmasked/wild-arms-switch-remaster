#include "gte_rtps_unr_reference.hpp"
#include "gte_rtps_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto regular=rtps_unr_reference(identity,{100,-50,200},{320,240,100});
static_assert(regular.projected.point.sx==370 && regular.projected.point.sy==215);
static_assert(regular.returned_sz3_shift2==50);
static_assert(regular.projected.quotient_q16==0x8000);
static_assert(!regular.projected.divide_overflow);
constexpr auto edge=rtps_unr_reference(identity,{1023,0,32767},{0,0,32767});
static_assert(edge.projected.point.sx==1022);
constexpr Transform translated{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto deep=rtps_unr_reference(translated,{10,0,0},{0,0,50000});
static_assert(deep.transformed.ir[2]==32767);
static_assert(deep.transformed.pre_ir[2]==50000);
static_assert(deep.projected.point.sz==50000);
static_assert(deep.returned_sz3_shift2==12500);
constexpr auto behind=rtps_unr_reference(identity,{0,0,-1},{0,0,100});
static_assert(behind.projected.divide_overflow);
static_assert(behind.projected.point.sz==0);
constexpr Transform very_deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,65535}}};
constexpr auto difference=rtps_unr_reference(very_deep,{1023,0,0},{0,0,65535});
constexpr auto old=rtps_reference(very_deep,{1023,0,0},{0,0,65535});
static_assert(difference.projected.quotient_q16==0xffff);
static_assert(difference.projected.point.sx==1022);
static_assert(old.projected.sx==1023);
int main(){ assert(regular.projected.point.sxy==pack_sxy(370,215)); }
