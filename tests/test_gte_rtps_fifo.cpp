#include "gte_rtps_fifo.hpp"
#include <cassert>
using namespace wa::gte;
constexpr auto seeded = RtpsFifoState{{10,20,30,40},{0x11110001u,0x22220002u,0x33330003u}};
constexpr auto shifted = push_rtps_fifo(seeded,50000,0xabcd1234u);
static_assert(shifted.sz[0]==20 && shifted.sz[1]==30 && shifted.sz[2]==40 && shifted.sz[3]==50000);
static_assert(shifted.sxy[0]==0x22220002u && shifted.sxy[1]==0x33330003u && shifted.sxy[2]==0xabcd1234u);
static_assert(seeded.sz[0]==10 && seeded.sxy[0]==0x11110001u);
constexpr auto shifted_again=push_rtps_fifo(shifted,0,0);
static_assert(shifted_again.sz[0]==30 && shifted_again.sz[3]==0);
static_assert(shifted_again.sxy[0]==0x33330003u && shifted_again.sxy[2]==0);
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr auto first=rtps_fifo_reference(seeded,identity,{100,-50,200},100,320*65536,240*65536,0,0);
static_assert(first.fifo.sz[0]==20 && first.fifo.sz[3]==200);
static_assert(first.fifo.sxy[2]==first.rtps.base.screen.sxy);
static_assert(first.rtps.base.screen.sx==370 && first.rtps.base.screen.sy==215);
constexpr auto second=rtps_fifo_reference(first.fifo,identity,{0,0,300},100,0,0,0,0);
static_assert(second.fifo.sz[0]==30 && second.fifo.sz[1]==40 && second.fifo.sz[2]==200 && second.fifo.sz[3]==300);
static_assert(second.fifo.sxy[0]==0x33330003u && second.fifo.sxy[1]==first.fifo.sxy[2]);
constexpr auto third=rtps_fifo_reference(second.fifo,identity,{0,0,-1},100,0,0,0,0);
static_assert(third.fifo.sz[0]==40 && third.fifo.sz[1]==200 && third.fifo.sz[2]==300 && third.fifo.sz[3]==0);
static_assert(third.rtps.base.depth.flags & (1u<<18));
int main(){assert(third.fifo.sz[3]==0);}
