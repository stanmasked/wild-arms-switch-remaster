#include "gte_projection.hpp"
#include <cassert>
using namespace wa::gte;
constexpr auto centered = project_reference(100,-50,200,{320,240,100});
static_assert(centered.sx==370 && centered.sy==215 && centered.sz==200);
static_assert(centered.sxy == pack_sxy(370,215));
constexpr auto near_point = project_reference(200,-200,0,{0,0,100});
static_assert(near_point.zero_or_negative_depth && near_point.ratio_saturated);
static_assert(near_point.sx==400 && near_point.sy==-400 && near_point.sz==0);
constexpr auto far_point = project_reference(100,100,100000,{0,0,100});
static_assert(far_point.depth_saturated && far_point.sz==65535);
constexpr auto saturating = project_reference(1000,-1000,10,{0,0,100});
static_assert(saturating.sx==1023 && saturating.sy==-1024);
static_assert(saturating.x_saturated && saturating.y_saturated);
constexpr auto negative = project_reference(-3,3,200,{0,0,100});
static_assert(negative.sx==-1 && negative.sy==1);
constexpr auto no_zoom = project_reference(1,1,200,{0,0,0});
static_assert(no_zoom.sx==0 && no_zoom.sy==0);
int main(){ assert(centered.sxy==pack_sxy(370,215)); }
