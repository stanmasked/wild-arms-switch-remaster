#include "gte_rtpt_reference.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr RtpsFifoState prior{{10,20,30,40},{11,22,33}};
constexpr std::array<Vector3,3> triangle{{{10,20,100},{20,30,200},{30,40,300}}};
constexpr auto triple=rtpt_reference(prior,identity,triangle,100,0,0,1,0);
static_assert(triple.fifo.sz[0]==40);
static_assert(triple.fifo.sz[1]==100 && triple.fifo.sz[2]==200 && triple.fifo.sz[3]==300);
static_assert(triple.fifo.sxy[0]==triple.stages[0].base.screen.sxy);
static_assert(triple.fifo.sxy[1]==triple.stages[1].base.screen.sxy);
static_assert(triple.fifo.sxy[2]==triple.stages[2].base.screen.sxy);
static_assert(triple.ir0==triple.stages[2].cue.ir0);
static_assert(triple.returned_sz3_shift2==75);
static_assert(triple.flag==0);
constexpr auto first=rtps_fifo_reference(prior,identity,triangle[0],100,0,0,1,0);
constexpr auto second=rtps_fifo_reference(first.fifo,identity,triangle[1],100,0,0,1,0);
constexpr auto third=rtps_fifo_reference(second.fifo,identity,triangle[2],100,0,0,1,0);
static_assert(third.fifo.sz==triple.fifo.sz && third.fifo.sxy==triple.fifo.sxy);
constexpr std::array<Vector3,3> problem{{{0,0,-1},{0,0,200},{0,0,300}}};
constexpr auto flagged=rtpt_reference({},identity,problem,100,0,0,0,0);
static_assert((flagged.flag&(1u<<18))!=0);
static_assert(flagged.stages[2].flag==0);
static_assert(flagged.fifo.sz[0]==0 && flagged.fifo.sz[1]==0);
static_assert(flagged.fifo.sz[2]==200 && flagged.fifo.sz[3]==300);
int main(){assert(triple.fifo.sz[3]==300);}
