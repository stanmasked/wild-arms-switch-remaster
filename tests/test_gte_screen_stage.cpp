#include "gte_screen_stage.hpp"
#include <cassert>
using namespace wa::gte;
static_assert(floor_shift16(-1) == -1);
static_assert(floor_shift16(-65536) == -1);
static_assert(wrap_i32(2147483648ll) == -2147483648ll);
constexpr auto normal=screen_stage_unr(100,-50,320*65536,240*65536,{0x8000,false});
static_assert(normal.sx==370 && normal.sy==215 && normal.flag==0);
constexpr auto fractional=screen_stage_unr(0,0,0x00018000,-0x00008000,{0x10000,false});
static_assert(fractional.sx==1 && fractional.sy==-1);
constexpr auto projected=screen_stage_unr(1023,0,0,0,{0xffff,false});
static_assert(projected.sx==1022);
constexpr auto clipping=screen_stage_unr(2000,-2000,0,0,{0x10000,true});
static_assert(clipping.sx==1023 && clipping.sy==-1024);
static_assert((clipping.flag & ((1u<<31)|(1u<<17)|(1u<<14)|(1u<<13))) ==
             ((1u<<31)|(1u<<17)|(1u<<14)|(1u<<13)));
constexpr auto overflow=screen_stage_unr(32767,0,2147483647,0,{0x10000,false});
static_assert((overflow.flag & (1u<<16)) != 0);
static_assert((overflow.flag & (1u<<31)) == 0); // MAC0 overflow alone is not summary.
int main(){assert(normal.sxy==pack_sxy(370,215));}
