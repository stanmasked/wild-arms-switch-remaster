#include "gte_rtps_mac44_depth_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto normal=rtps_mac44_depth_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(normal.screen.sx==370 && normal.screen.sy==215);
static_assert(normal.depth.sz3==200 && normal.returned_sz3_shift2==50);
static_assert(normal.flag==0);
constexpr auto previous=rtps_mac44_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(normal.screen.sxy==previous.screen.sxy);
constexpr Transform deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto shifted=rtps_mac44_depth_reference(deep,{0,0,0},100,0,0);
static_assert(shifted.depth.ir3==32767 && shifted.depth.sz3==50000);
static_assert(shifted.flag==(1u<<22));
constexpr Transform sf0_case{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,12}}};
constexpr auto unshifted=rtps_mac44_depth_reference(sf0_case,{0,0,0},100,0,0,false,false);
static_assert(unshifted.depth.ir3==32767 && unshifted.depth.sz3==12);
static_assert((unshifted.flag&(1u<<22))==0);
constexpr auto behind=rtps_mac44_depth_reference(identity,{0,0,-1},100,0,0);
static_assert(behind.depth.sz3==0);
static_assert((behind.flag&((1u<<18)|(1u<<17)|(1u<<31)))==((1u<<18)|(1u<<17)|(1u<<31)));
int main(){assert(normal.returned_sz3_shift2==50);}
