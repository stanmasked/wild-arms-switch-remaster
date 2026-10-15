#include "gte_rtps_mac44_reference.hpp"
#include "gte_rtps_mac_reference.hpp"
#include <cassert>
#include <cstdint>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto normal=rtps_mac44_reference(identity,{100,-50,200},100,320*65536,240*65536);
constexpr auto old_normal=rtps_mac_reference(identity,{100,-50,200},100,320*65536,240*65536);
static_assert(normal.flag==old_normal.flag && normal.flag==0);
static_assert(normal.screen.sxy==old_normal.screen.sxy);
static_assert(normal.returned_sz3_shift2==50);
constexpr Transform deep{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,50000}}};
constexpr auto z=rtps_mac44_reference(deep,{1,2,0},50000,0,0);
static_assert(z.sz3==50000 && z.mac_ir.ir[2]==32767);
static_assert(z.returned_sz3_shift2==12500);
// The first multiply crosses +2^43, the next crosses back below it.
// A final-sum-only detector misses the intermediate overflow.
constexpr Transform transient{{{{32767,-32768,0},{0,4096,0},{0,0,4096}}},{{INT32_MAX,0,200}}};
constexpr auto step=rtps_mac44_reference(transient,{32767,32767,0},100,0,0);
constexpr auto legacy=rtps_mac_reference(transient,{32767,32767,0},100,0,0);
static_assert(step.matrix.accumulators[0].positive_overflow);
static_assert((step.flag & (1u<<30))!=0);
static_assert((legacy.flag & (1u<<30))==0);
static_assert(step.matrix.accumulators[0].value==legacy.raw_mac[0]);
static_assert(step.mac_ir.mac[0]==legacy.mac_ir.mac[0]);
constexpr Transform persist{{{{32767,0,0},{0,4096,0},{0,0,4096}}},{{INT32_MAX,0,200}}};
constexpr auto wrapped=rtps_mac44_reference(persist,{32767,0,0},100,0,0);
static_assert(wrapped.matrix.accumulators[0].positive_overflow);
static_assert(wrapped.matrix.accumulators[0].value<0);
static_assert((wrapped.flag & ((1u<<30)|(1u<<31)))==((1u<<30)|(1u<<31)));
int main(){assert(normal.screen.sxy==pack_sxy(370,215));}
