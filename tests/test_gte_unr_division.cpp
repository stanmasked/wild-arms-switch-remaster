#include "gte_unr_division.hpp"
#include <cassert>
using namespace wa::gte;
static_assert(unr_table_entry(0) == 0xff);
static_assert(unr_table_entry(1) == 0xfd);
static_assert(unr_table_entry(255) == 0);
static_assert(unr_table_entry(256) == 0);
static_assert(gte_unr_divide(0, 0).quotient == 0x1ffff);
static_assert(gte_unr_divide(0, 0).divide_overflow);
static_assert(gte_unr_divide(0, 1).quotient == 0);
static_assert(!gte_unr_divide(0, 1).divide_overflow);
static_assert(gte_unr_divide(1, 1).quotient == 0x10000);
static_assert(gte_unr_divide(2, 1).quotient == 0x1ffff);
static_assert(gte_unr_divide(2, 1).divide_overflow);
static_assert(gte_unr_divide(100, 200).quotient == 0x8000);
static_assert(!gte_unr_divide(100, 200).divide_overflow);
static_assert(gte_unr_divide(200, 100).divide_overflow);
static_assert(gte_unr_divide(0xffff, 0xffff).quotient == 0xffff);
int main() {
    for (unsigned d=1; d<=65535; ++d) {
        const auto zero=gte_unr_divide(0, static_cast<std::uint16_t>(d));
        assert(zero.quotient==0 && !zero.divide_overflow);
        const auto saturated=gte_unr_divide(static_cast<std::uint16_t>((d<32768)?d*2:65535), static_cast<std::uint16_t>(d));
        if(d<32768) assert(saturated.divide_overflow && saturated.quotient==0x1ffff);
        else assert(saturated.quotient<=0x1ffff);
    }
}
