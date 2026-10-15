#include "core.hpp"
#include <algorithm>
namespace wa {
void update(State& state, const Input& input) {
  if (input.toggle_mode && !state.previous_toggle)
    state.mode = state.mode == GraphicsMode::Original ? GraphicsMode::HD : GraphicsMode::Original;
  state.previous_toggle = input.toggle_mode;
  if (input.left != input.right) state.cursor_x = std::clamp(state.cursor_x + (input.right ? 1 : -1), 0, 19);
  ++state.frames;
}
}
