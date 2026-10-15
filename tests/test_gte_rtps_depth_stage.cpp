#include "gte_rtps_depth_stage.hpp"
#include <cassert>
using namespace wa::gte;
static_assert(rtps_depth_stage(50000,true,false).ir3==32767);
static_assert(rtps_depth_stage(50000,true,false).sz3==50000);
static_assert(rtps_depth_stage(50000,true,false).flags==(1u<<22));
static_assert(rtps_depth_stage(50000,false,false).ir3==32767);
static_assert(rtps_depth_stage(50000,false,false).sz3==12);
static_assert(rtps_depth_stage(50000,false,false).flags==0);
static_assert(rtps_depth_stage(-1,false,false).sz3==0);
static_assert(rtps_depth_stage(-1,false,false).flags==((1u<<18)|(1u<<31)));
static_assert(rtps_depth_stage(-1,false,true).ir3==0);
static_assert(rtps_depth_stage(140000000,false,false).flags==(1u<<22));
static_assert(rtps_depth_stage(65536,true,false).flags==((1u<<22)|(1u<<18)|(1u<<31)));
static_assert(rtps_depth_stage(-32769,true,false).flags==((1u<<22)|(1u<<18)|(1u<<31)));
static_assert(rtps_depth_stage(32767,true,false).flags==0);
static_assert(rtps_depth_stage(65535,true,false).sz3==65535);
int main(){assert(rtps_depth_stage(0,true,false).flags==0);}
