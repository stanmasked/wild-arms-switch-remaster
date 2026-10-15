#include "core.hpp"
#include <cassert>
int main() {
  wa::State s;
  assert(s.mode == wa::GraphicsMode::Original);
  wa::update(s, {.toggle_mode=true});
  assert(s.mode == wa::GraphicsMode::HD);
  wa::update(s, {.toggle_mode=true});
  assert(s.mode == wa::GraphicsMode::HD);
  wa::update(s, {});
  wa::update(s, {.toggle_mode=true, .right=true});
  assert(s.mode == wa::GraphicsMode::Original && s.cursor_x == 1);
  for(int i=0;i<30;++i) wa::update(s, {.left=true});
  assert(s.cursor_x == 0 && s.frames == 34);
}
