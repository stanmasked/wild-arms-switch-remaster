#include "gte_triangle_classification.hpp"
#include <cassert>
using namespace wa::gte;
constexpr auto positive = nclip_reference({pack_sxy(0,0),pack_sxy(100,0),pack_sxy(0,100)});
constexpr auto negative = nclip_reference({pack_sxy(0,0),pack_sxy(0,100),pack_sxy(100,0)});
static_assert(classify_nclip(positive,FrontFace::PositiveArea).kind == TriangleClass::FrontFacing);
static_assert(!classify_nclip(positive,FrontFace::PositiveArea).safe_to_cull);
static_assert(classify_nclip(positive,FrontFace::NegativeArea).safe_to_cull);
static_assert(classify_nclip(negative,FrontFace::NegativeArea).kind == TriangleClass::FrontFacing);
static_assert(classify_nclip(negative,FrontFace::PositiveArea).kind == TriangleClass::BackFacing);
constexpr auto zero = nclip_reference({pack_sxy(5,5),pack_sxy(5,5),pack_sxy(20,30)});
static_assert(classify_nclip(zero,FrontFace::PositiveArea).kind == TriangleClass::Degenerate);
static_assert(!classify_nclip(zero,FrontFace::PositiveArea).safe_to_cull);
constexpr auto overflow = nclip_reference({
    pack_sxy(-32768,-32768),pack_sxy(32767,-32768),pack_sxy(-32768,32767)});
static_assert(overflow.flag & (1u<<16));
static_assert(classify_nclip(overflow,FrontFace::PositiveArea).kind == TriangleClass::IndeterminateOverflow);
static_assert(!classify_nclip(overflow,FrontFace::PositiveArea).safe_to_cull);
constexpr auto reverse_overflow = nclip_reference({
    pack_sxy(-32768,-32768),pack_sxy(-32768,32767),pack_sxy(32767,-32768)});
static_assert(reverse_overflow.flag & (1u<<15));
static_assert(classify_nclip(reverse_overflow,FrontFace::NegativeArea).kind == TriangleClass::IndeterminateOverflow);
constexpr Transform identity{{{{4096,0,0},{0,4096,0},{0,0,4096}}},{{0,0,0}}};
constexpr std::array<Vector3,3> vertices{{{0,0,100},{100,0,100},{0,100,100}}};
constexpr auto front = rtpt_classify_triangle({},identity,vertices,100,0,0,0,0,FrontFace::PositiveArea);
static_assert(front.geometry.nclip.mac0 == 10000);
static_assert(front.facing.kind == TriangleClass::FrontFacing);
constexpr auto back = rtpt_classify_triangle({},identity,vertices,100,0,0,0,0,FrontFace::NegativeArea);
static_assert(back.facing.safe_to_cull);
static_assert(back.geometry.rtpt.fifo.sz[3] == 100);
int main(){assert(!front.facing.safe_to_cull && back.facing.safe_to_cull);}
