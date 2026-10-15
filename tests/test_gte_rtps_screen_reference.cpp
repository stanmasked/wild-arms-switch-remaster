#include "gte_rtps_screen_reference.hpp"
#include "gte_rtps_unr_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto standard = rtps_screen_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(standard.screen.sx == 370 && standard.screen.sy == 215);
static_assert(standard.sz3 == 200 && standard.returned_sz3_shift2 == 50);
static_assert(standard.ratio.quotient == 0x8000 && standard.screen.flag == 0);
constexpr auto legacy = rtps_unr_reference(identity,{100,-50,200},{320,240,100});
static_assert(legacy.projected.point.sxy == standard.screen.sxy);
constexpr auto fractional = rtps_screen_reference(identity,{0,0,200},100,0x18000,-0x8000);
static_assert(fractional.screen.sx == 1 && fractional.screen.sy == -1);
constexpr auto overflow = rtps_screen_reference(identity,{5,-5,0},100,0,0);
static_assert(overflow.ratio.divide_overflow);
static_assert((overflow.screen.flag & (1u<<17)) != 0);
constexpr Transform deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto depth = rtps_screen_reference(deep,{10,0,0},50000,0,0);
static_assert(depth.transformed.ir[2] == 32767 && depth.sz3 == 50000);
static_assert(depth.returned_sz3_shift2 == 12500);
constexpr auto edge = rtps_screen_reference(identity,{1023,0,32767},32767,0,0);
static_assert(edge.screen.sx == 1022);
int main() {assert(standard.screen.sxy == pack_sxy(370,215));}
