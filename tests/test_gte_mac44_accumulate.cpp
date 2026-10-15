#include "gte_mac44_accumulate.hpp"
#include <cassert>
using namespace wa::gte;
constexpr std::int64_t mx = (std::int64_t{1}<<43)-1;
constexpr std::int64_t mn = -(std::int64_t{1}<<43);
static_assert(wrap_signed44(mx)==mx);
static_assert(wrap_signed44(mn)==mn);
static_assert(wrap_signed44(mx+1)==mn);
static_assert(wrap_signed44(mn-1)==mx);
constexpr auto pos=mac44_add({mx,false,false},1);
static_assert(pos.value==mn && pos.positive_overflow && !pos.negative_overflow);
constexpr auto neg=mac44_add({mn,false,false},-1);
static_assert(neg.value==mx && neg.negative_overflow && !neg.positive_overflow);
constexpr auto twice=mac44_add(mac44_add({mx,false,false},1),-1);
static_assert(twice.value==mx && twice.positive_overflow);
static_assert(twice.negative_overflow);
constexpr std::array<std::array<std::int16_t,3>,3> identity{{{4096,0,0},{0,4096,0},{0,0,4096}}};
constexpr auto regular=matrix44_accumulate(identity,{0,0,0},{3,-5,10});
static_assert(regular.flag==0 && regular.accumulators[0].value==12288);
static_assert(regular.accumulators[1].value==-20480);
constexpr auto large=matrix44_accumulate(identity,{2147483647,0,0},{32767,0,0});
static_assert(large.accumulators[0].positive_overflow);
static_assert((large.flag & ((1u<<30)|(1u<<31)))==((1u<<30)|(1u<<31)));
int main(){assert(regular.flag==0);}
