#include "gte_math.hpp"
#include <cassert>
int main() {
    using namespace wa::gte;
    static_assert(floor_shift12(4097) == 1);
    static_assert(floor_shift12(-1) == -1);
    static_assert(floor_shift12(-4096) == -1);
    static_assert(floor_shift12(-4097) == -2);
    static_assert(clamp_ir_signed(-33000) == -32768);
    static_assert(clamp_ir_signed(50000) == 32767);
    static_assert(clamp_ir_signed(-5) == -5);
    static_assert(clamp_ir_unsigned(-1) == 0);
    static_assert(clamp_ir_unsigned(123) == 123);
    static_assert(clamp_ir_unsigned(50000) == 32767);
    static_assert(clamp_sz(-1) == 0);
    static_assert(clamp_sz(100) == 100);
    static_assert(clamp_sz(99999) == 65535);
    static_assert(clamp_sx(-1200) == -1024);
    static_assert(clamp_sx(3000) == 1023);
    static_assert(clamp_sy(-1200) == -1024);
    static_assert(clamp_sy(3000) == 1023);
    static_assert(pack_sxy(-1, 24) == 0x0018ffffu);
    static_assert(pack_sxy(-1024, -1) == 0xfffffc00u);
    assert(pack_sxy(clamp_sx(2000), clamp_sy(-2000)) == 0xfc0003ffu);
}
