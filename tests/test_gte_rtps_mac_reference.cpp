#include "gte_rtps_mac_reference.hpp"
#include "gte_rtps_screen_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto normal = rtps_mac_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(normal.screen.sx == 370 && normal.screen.sy == 215);
static_assert(normal.mac_ir.mac[0] == 100 && normal.mac_ir.ir[1] == -50);
static_assert(normal.sz3 == 200 && normal.returned_sz3_shift2 == 50 && normal.flag == 0);
constexpr auto baseline = rtps_screen_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(normal.screen.sxy == baseline.screen.sxy);
constexpr Transform deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto z = rtps_mac_reference(deep,{1,2,0},50000,0,0);
static_assert(z.mac_ir.ir[2] == 32767 && z.sz3 == 50000);
static_assert((z.flag & (1u<<22)) && !(z.flag & (1u<<31)));
constexpr auto zero = rtps_mac_reference(identity,{0,0,0},100,0,0);
static_assert(zero.ratio.divide_overflow && (zero.flag & (1u<<17)) && (zero.flag & (1u<<31)));
constexpr auto neg = rtps_mac_reference(identity,{0,0,-10},100,0,0);
static_assert(neg.sz3 == 0 && (neg.flag & (1u<<18)));
constexpr Transform clip{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{50000,0,200}}};
constexpr auto x = rtps_mac_reference(clip,{0,0,0},100,0,0);
static_assert(x.mac_ir.ir[0] == 32767 && (x.flag & (1u<<24)) && (x.flag & (1u<<31)));
int main() { assert(normal.screen.sxy == pack_sxy(370,215)); }
