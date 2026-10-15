#pragma once
#include <cstdint>
namespace wa {
enum class GraphicsMode { Original, HD };
struct Input { bool toggle_mode = false; bool left = false; bool right = false; };
struct State { GraphicsMode mode = GraphicsMode::Original; int cursor_x = 0; std::uint64_t frames = 0; bool previous_toggle = false; };
void update(State& state, const Input& input);
}
