#include "gte_mac_stage.hpp"
#include <cassert>
using namespace wa::gte;
constexpr auto ordinary=mac_ir_from_raw({4096*3,-4096*5,4096*17});
static_assert(ordinary.mac[0]==3 && ordinary.ir[1]==-5 && ordinary.flag==0);
constexpr auto clip=mac_ir_from_raw({4096LL*50000,0,0});
static_assert(clip.ir[0]==32767 && (clip.flag & (1u<<24)) && (clip.flag & (1u<<31)));
constexpr auto ir3_only=mac_ir_from_raw({0,0,4096LL*40000});
static_assert(ir3_only.ir[2]==32767 && ir3_only.flag==(1u<<22));
constexpr auto lm=mac_ir_from_raw({-4096,0,4096},true,true);
static_assert(lm.ir[0]==0 && (lm.flag & (1u<<24)));
constexpr auto pos=mac_ir_from_raw({(1LL<<43),0,0},false);
static_assert((pos.flag & (1u<<30)) && (pos.flag & (1u<<31)));
constexpr auto neg=mac_ir_from_raw({0,-(1LL<<43)-1,0},false);
static_assert((neg.flag & (1u<<26)) && (neg.flag & (1u<<31)));
constexpr auto boundary=mac_ir_from_raw({(1LL<<43)-1,-(1LL<<43),0},false);
static_assert((boundary.flag & ((1u<<30)|(1u<<27)|(1u<<29)|(1u<<26)))==0);
constexpr auto wrap=mac_ir_from_raw({4294967295LL,0,0},false);
static_assert(wrap.mac[0]==-1 && wrap.flag==0);
constexpr auto negative_rounding=mac_ir_from_raw({-1,0,0});
static_assert(negative_rounding.mac[0]==-1);
int main(){assert(ordinary.flag==0);}
