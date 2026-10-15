#include "gte_transform.hpp"
#include <cassert>
using namespace wa::gte;
constexpr Transform identity{{{{4096, 0, 0}, {0, 4096, 0}, {0, 0, 4096}}}, {{0, 0, 0}}};
constexpr auto p = rotate_translate(identity, {12, -15, 150});
static_assert(p.ir[0] == 12 && p.ir[1] == -15 && p.ir[2] == 150);
static_assert(!p.clamped[0] && !p.clamped[1] && !p.clamped[2]);
constexpr Transform shifted{{{{4096, 0, 0}, {0, 4096, 0}, {0, 0, 4096}}}, {{25, -3, 7}}};
constexpr auto t = rotate_translate(shifted, {1, 2, 3});
static_assert(t.ir[0] == 26 && t.ir[1] == -1 && t.ir[2] == 10);
constexpr Transform half_x{{{{2048, 0, 0}, {0, 4096, 0}, {0, 0, 4096}}}, {{0, 0, 0}}};
constexpr auto n = rotate_translate(half_x, {-3, 0, 0});
static_assert(n.ir[0] == -2);
constexpr Transform saturated{{{{4096, 0, 0}, {0, 4096, 0}, {0, 0, 4096}}}, {{50000, -50000, 0}}};
constexpr auto s = rotate_translate(saturated, {0, 0, 0});
static_assert(s.ir[0] == 32767 && s.ir[1] == -32768);
static_assert(s.clamped[0] && s.clamped[1]);
constexpr auto lm = rotate_translate(identity, {-1, -2, 3}, true);
static_assert(lm.ir[0] == 0 && lm.ir[1] == 0 && lm.ir[2] == 3);
static_assert(lm.clamped[0] && lm.clamped[1] && !lm.clamped[2]);
int main() { assert(p.ir[2] == 150); }
