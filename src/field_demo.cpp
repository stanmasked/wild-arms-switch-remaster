#include "field.hpp"
#include "field_view.hpp"

#include <iostream>

int main() {
  using namespace wa::field;
  const Map map{
      11, 7,
      "###########"
      "#...!.....#"
      "#.#.###.#.#"
      "#...#...#.#"
      "#.#...#...#"
      "#.....E...#"
      "###########"};
  State player{1, 1};

  std::cout << "Wild Arms field prototype (original assets not included)\n"
            << "Walk with W/A/S/D, quit with Q. ! = event, E = exit.\n";
  if (!map.valid()) return 1;

  for (;;) {
    RenderFrame frame;
    if (build_view(frame, map, player, Viewport{9, 5}) !=
        RenderOutcome::Ready)
      return 1;
    for (int y = 0; y < frame.height; ++y) {
      for (int x = 0; x < frame.width; ++x) {
        const RenderCell* cell = frame.at(x, y);
        if (!cell) return 1;
        std::cout << glyph_for(*cell, frame.player_facing);
      }
      std::cout << '\n';
    }
    std::cout << "Moves: " << player.successful_moves << " > " << std::flush;
    char key = 0;
    if (!(std::cin >> key)) return 0;
    Input input;
    switch (key) {
      case 'w': case 'W': input.up = true; break;
      case 's': case 'S': input.down = true; break;
      case 'a': case 'A': input.left = true; break;
      case 'd': case 'D': input.right = true; break;
      case 'q': case 'Q': return 0;
      default:
        std::cout << "Use W/A/S/D or Q.\n";
        continue;
    }
    const Result result = step(player, map, input);
    if (result.outcome == Outcome::Blocked) {
      std::cout << "The path is blocked.\n";
    } else if (result.outcome != Outcome::Moved) {
      std::cout << "No valid move.\n";
    }
    if (result.trigger == Trigger::Event) {
      std::cout << "Field event reached (script system not implemented).\n";
    } else if (result.trigger == Trigger::Exit) {
      std::cout << "Exit reached! A future map transition will go here.\n";
      return 0;
    }
  }
}
