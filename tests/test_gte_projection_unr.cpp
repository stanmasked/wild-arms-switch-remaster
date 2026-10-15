#include "gte_projection_unr.hpp"
#include <cassert>
using namespace wa::gte;
constexpr ProjectionParameters origin{0,0,65535};
constexpr auto edge = project_unr_reference(1023,0,65535,origin);
static_assert(edge.quotient_q16 == 0xffff);
static_assert(edge.point.sx == 1022);
static_assert(project_reference(1023,0,65535,origin).sx == 1023);
constexpr auto overflow = project_unr_reference(5,-5,0,{0,0,100});
static_assert(overflow.divide_overflow && overflow.quotient_q16 == 0x1ffff);
static_assert(overflow.point.sx == 9 && overflow.point.sy == -9);
constexpr auto regular = project_unr_reference(100,-50,200,{320,240,100});
static_assert(regular.quotient_q16 == 0x8000);
static_assert(regular.point.sx == 370 && regular.point.sy == 215);
constexpr auto shifted = project_unr_reference(1,1,200,{0,0,0});
static_assert(!shifted.divide_overflow && shifted.quotient_q16==0);
constexpr auto far = project_unr_reference(1023,1023,100000,{0,0,65535});
static_assert(far.point.depth_saturated && far.point.sz == 65535);
int main() {assert(edge.point.sxy == pack_sxy(1022,0));}
