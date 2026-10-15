#include "gte_rtps_ir0_reference.hpp"
#include <array>
#include <cstdint>
#include <iostream>

int main() {
    // 22 signed decimal integers: matrix[9], translation[3], vertex[3],
    // H, OFX, OFY, DQA, DQB, SF, LM.
    std::array<std::int64_t,22> words{};
    for (auto& value : words)
        if (!(std::cin >> value)) return 2;
    wa::gte::Transform transform{};
    unsigned i = 0;
    for (auto& row : transform.rotation)
        for (auto& cell : row)
            cell = static_cast<std::int16_t>(words[i++]);
    for (auto& value : transform.translation)
        value = static_cast<std::int32_t>(words[i++]);
    wa::gte::Vector3 vertex{
        static_cast<std::int16_t>(words[i]),
        static_cast<std::int16_t>(words[i+1]),
        static_cast<std::int16_t>(words[i+2])};
    i += 3;
    const auto h = static_cast<std::uint16_t>(words[i++]);
    const auto ofx = static_cast<std::int32_t>(words[i++]);
    const auto ofy = static_cast<std::int32_t>(words[i++]);
    const auto dqa = static_cast<std::int16_t>(words[i++]);
    const auto dqb = static_cast<std::int32_t>(words[i++]);
    const bool sf = words[i++] != 0, lm = words[i++] != 0;
    const auto result = wa::gte::rtps_ir0_reference(
        transform,vertex,h,ofx,ofy,dqa,dqb,sf,lm);
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
