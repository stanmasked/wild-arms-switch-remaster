#include "gte_rtps_ir0_reference.hpp"
#include <array>
#include <cstdint>
#include <iostream>
#include <limits>

namespace {
constexpr bool valid_input(std::size_t index, std::int64_t value) noexcept {
    if (index <= 8 || (index >= 12 && index <= 14) || index == 18)
        return value >= -32768 && value <= 32767;
    if ((index >= 9 && index <= 11) || index == 16 || index == 17 || index == 19)
        return value >= std::numeric_limits<std::int32_t>::min() &&
               value <= std::numeric_limits<std::int32_t>::max();
    if (index == 15) return value >= 0 && value <= 65535;
    return value == 0 || value == 1; // sf / lm
}
}

int main() {
    // 22 decimal integer inputs: matrix[9], translation[3], vertex[3], H,
    // OFX, OFY, DQA, DQB, SF, LM. No implicit narrowing on untrusted data.
    std::array<std::int64_t, 22> words{};
    for (std::size_t n = 0; n < words.size(); ++n) {
        if (!(std::cin >> words[n]) || !valid_input(n, words[n])) {
            std::cerr << "invalid GTE input at index " << n << '\n';
            return 2;
        }
    }
    std::string trailing;
    if (std::cin >> trailing) {
        std::cerr << "unexpected extra GTE input\n";
        return 2;
    }
    if (!std::cin.eof()) {
        std::cerr << "malformed trailing GTE input\n";
        return 2;
    }
    wa::gte::Transform transform{};
    unsigned i = 0;
    for (auto& row : transform.rotation)
        for (auto& cell : row) cell = static_cast<std::int16_t>(words[i++]);
    for (auto& value : transform.translation)
        value = static_cast<std::int32_t>(words[i++]);
    wa::gte::Vector3 vertex{
        static_cast<std::int16_t>(words[i]),
        static_cast<std::int16_t>(words[i + 1]),
        static_cast<std::int16_t>(words[i + 2])};
    i += 3;
    const auto h = static_cast<std::uint16_t>(words[i++]);
    const auto ofx = static_cast<std::int32_t>(words[i++]);
    const auto ofy = static_cast<std::int32_t>(words[i++]);
    const auto dqa = static_cast<std::int16_t>(words[i++]);
    const auto dqb = static_cast<std::int32_t>(words[i++]);
    const bool sf = words[i++] != 0;
    const bool lm = words[i++] != 0;
    const auto result = wa::gte::rtps_ir0_reference(
        transform, vertex, h, ofx, ofy, dqa, dqb, sf, lm);
    std::cout << result.base.screen.sxy << ' '
              << result.base.depth.sz3 << ' '
              << result.cue.ir0 << ' '
              << result.base.mac_ir.ir[0] << ' '
              << result.base.mac_ir.ir[1] << ' '
              << result.base.mac_ir.ir[2] << ' '
              << result.cue.mac0 << ' '
              << result.base.mac_ir.mac[0] << ' '
              << result.base.mac_ir.mac[1] << ' '
              << result.base.mac_ir.mac[2] << ' '
              << result.flag << '\n';
}
