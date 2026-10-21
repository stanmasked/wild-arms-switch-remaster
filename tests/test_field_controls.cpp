#include "field_controls.hpp"
#include "field_view.hpp"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <limits>

namespace {
using namespace wa::field;

void require(bool condition) {
  if (!condition) std::abort();
}

bool no_direction(const Input& i) {
  return !i.up && !i.down && !i.left && !i.right;
}

Map corridor() {
  return {8, 3,
          "########"
          "#..!E..#"
          "########"};
}

void test_stick_deadzone_and_full_int16_range() {
  PadDecoder d;
  require(no_direction(decode_pad(d, {.stick_x = 15999}).direction));
  require(no_direction(decode_pad(d, {.stick_y = -15999}).direction));
  require(decode_pad(d, {.stick_x = 16000}).direction.right);
  require(decode_pad(d, {.stick_x = -16000}).direction.left);
  require(decode_pad(d, {.stick_y = -16000}).direction.up);
  require(decode_pad(d, {.stick_y = 16000}).direction.down);
  require(decode_pad(d, {.stick_x =
      std::numeric_limits<std::int16_t>::min()}).direction.left);
  require(decode_pad(d, {.stick_x =
      std::numeric_limits<std::int16_t>::max()}).direction.right);
  const auto diagonal = decode_pad(d, {.stick_x = 25000, .stick_y = -26000});
  require(diagonal.direction.right && diagonal.direction.up &&
          !diagonal.direction.down && !diagonal.direction.left);
}

void test_dpad_precedence_and_conflicting_inputs() {
  PadDecoder d;
  const auto c = decode_pad(d, {.dpad_left = true, .stick_x = 30000});
  require(c.direction.left && !c.direction.right);
  const auto opposing =
      decode_pad(d, {.dpad_up = true, .dpad_down = true, .stick_x = 30000});
  require(opposing.direction.up && opposing.direction.down &&
          !opposing.direction.right);
  State s{1, 1};
  MovementClock clock;
  const auto result = advance_pad_frame(d, clock, s, corridor(),
      {.dpad_up = true, .dpad_down = true}, 160);
  require(result.movement.status == TimedStatus::AmbiguousInput);
  require(s.x == 1 && s.y == 1 && clock.carry_ms == 0);
  const auto diagonal = advance_pad_frame(d, clock, s, corridor(),
      {.stick_x = 22000, .stick_y = 22000}, 160);
  require(diagonal.movement.status == TimedStatus::AmbiguousInput);
  require(s.successful_moves == 0);
}

void test_confirm_rising_edge() {
  PadDecoder d;
  require(!decode_pad(d, {}).confirm_pressed);
  require(decode_pad(d, {.confirm = true}).confirm_pressed);
  require(!decode_pad(d, {.confirm = true}).confirm_pressed);
  require(!decode_pad(d, {}).confirm_pressed);
  require(decode_pad(d, {.confirm = true}).confirm_pressed);
}

void test_event_and_exit_require_new_confirm() {
  const Map map = corridor();
  require(map.valid());
  State s{1, 1};
  MovementClock clock;
  PadDecoder decoder;
  const PadSample right{.dpad_right = true};

  auto first = advance_pad_frame(decoder, clock, s, map, right, 160);
  require(first.movement.status == TimedStatus::Moved && s.x == 2);
  auto event = advance_pad_frame(decoder, clock, s, map, right, 160);
  require(event.movement.status == TimedStatus::Triggered &&
          event.movement.trigger == Trigger::Event && s.x == 3);
  require(clock.paused_for_trigger);

  const PadSample press{.dpad_right = true, .confirm = true};
  const auto ack = advance_pad_frame(decoder, clock, s, map, press, 160);
  require(ack.outcome == PadFrameOutcome::Acknowledged &&
          ack.movement.attempted_steps == 0 && s.x == 3);
  require(!clock.paused_for_trigger);

  const auto exit = advance_pad_frame(decoder, clock, s, map, press, 160);
  require(exit.outcome == PadFrameOutcome::Advanced &&
          exit.movement.status == TimedStatus::Triggered &&
          exit.movement.trigger == Trigger::Exit && s.x == 4);
  require(advance_pad_frame(decoder, clock, s, map, press, 160)
              .movement.status == TimedStatus::Paused);
  require(clock.paused_for_trigger);
  require(advance_pad_frame(decoder, clock, s, map, right, 0)
              .movement.status == TimedStatus::Paused);
  const auto resume = advance_pad_frame(decoder, clock, s, map, press, 160);
  require(resume.outcome == PadFrameOutcome::Acknowledged &&
          !clock.paused_for_trigger && s.x == 4);
}

void test_holding_confirm_before_event_never_auto_acknowledges() {
  State s{1, 1};
  MovementClock clock;
  PadDecoder decoder;
  const Map map = corridor();
  const PadSample held{.dpad_right = true, .confirm = true};
  require(advance_pad_frame(decoder, clock, s, map, held, 160)
              .movement.status == TimedStatus::Moved);
  require(advance_pad_frame(decoder, clock, s, map, held, 160)
              .movement.trigger == Trigger::Event);
  require(advance_pad_frame(decoder, clock, s, map, held, 160)
              .movement.status == TimedStatus::Paused);
  require(clock.paused_for_trigger && s.x == 3);
  (void)advance_pad_frame(decoder, clock, s, map, {}, 0);
  const auto fresh = advance_pad_frame(decoder, clock, s, map,
                                      {.confirm = true}, 0);
  require(fresh.outcome == PadFrameOutcome::Acknowledged &&
          !clock.paused_for_trigger && s.x == 3);
}

void test_invalid_updates_do_not_consume_edges() {
  const Map m = corridor();
  State s{1, 1};
  MovementClock clock;
  PadDecoder decoder;
  const PadSample confirm{.confirm = true};
  require(advance_pad_frame(decoder, clock, s, m, confirm, 1001)
              .movement.status == TimedStatus::InvalidDelta);
  require(!decoder.confirm_down);
  require(advance_pad_frame(decoder, clock, s,
                           Map{1, 1, "?"}, confirm, 0)
              .movement.status == TimedStatus::InvalidMap);
  require(!decoder.confirm_down);
  State invalid{-1, 1};
  require(advance_pad_frame(decoder, clock, invalid, m, confirm, 0)
              .movement.status == TimedStatus::InvalidState);
  require(!decoder.confirm_down);
  clock.cadence_ms = 0;
  require(advance_pad_frame(decoder, clock, s, m, confirm, 0)
              .movement.status == TimedStatus::InvalidClock);
  require(!decoder.confirm_down && s.successful_moves == 0);
}

struct Playback {
  State state{1, 1};
  MovementClock clock;
  PadDecoder decoder;
  RenderFrame frame;
  std::uint32_t event_count = 0;
  std::uint32_t exit_count = 0;
};

void replay_tick(Playback& play, const Map& m, const PadSample& pad,
                 std::uint32_t elapsed_ms) {
  const auto result =
      advance_pad_frame(play.decoder, play.clock, play.state, m, pad, elapsed_ms);
  require(result.movement.status != TimedStatus::InvalidMap &&
          result.movement.status != TimedStatus::InvalidState &&
          result.movement.status != TimedStatus::InvalidClock &&
          result.movement.status != TimedStatus::InvalidDelta);
  if (result.movement.trigger == Trigger::Event) ++play.event_count;
  if (result.movement.trigger == Trigger::Exit) ++play.exit_count;
  require(build_view(play.frame, m, play.state, {5, 3}) ==
          RenderOutcome::Ready);
}

void test_deterministic_controller_to_viewport_replay() {
  const Map m = corridor();
  const std::array<PadSample, 8> inputs{{
      {.stick_x = 21000}, {.stick_x = 21000},
      {.dpad_right = true, .confirm = true},
      {.dpad_right = true, .confirm = true},
      {.dpad_right = true, .confirm = true},
      {.dpad_right = true},
      {.confirm = true},
      {}
  }};
  const std::array<std::uint32_t, 8> durations{{
      160, 160, 160, 160, 160, 0, 160, 0
  }};
  Playback a, b;
  for (std::size_t i = 0; i < inputs.size(); ++i) {
    replay_tick(a, m, inputs[i], durations[i]);
    replay_tick(b, m, inputs[i], durations[i]);
    require(a.state.x == b.state.x && a.state.y == b.state.y &&
            a.state.facing == b.state.facing &&
            a.state.successful_moves == b.state.successful_moves);
    require(a.clock.carry_ms == b.clock.carry_ms &&
            a.clock.paused_for_trigger == b.clock.paused_for_trigger &&
            a.clock.held == b.clock.held);
    require(a.decoder.confirm_down == b.decoder.confirm_down);
    require(a.event_count == b.event_count &&
            a.exit_count == b.exit_count);
    require(a.frame.world_left == b.frame.world_left &&
            a.frame.world_top == b.frame.world_top);
    for (int y = 0; y < a.frame.height; ++y)
      for (int x = 0; x < a.frame.width; ++x) {
        require(a.frame.at(x, y)->terrain == b.frame.at(x, y)->terrain);
        require(a.frame.at(x, y)->player == b.frame.at(x, y)->player);
      }
  }
  require(a.event_count == 1 && a.exit_count == 1 &&
          a.state.x == 4 && a.state.successful_moves == 3);
}

}  // namespace

int main() {
  test_stick_deadzone_and_full_int16_range();
  test_dpad_precedence_and_conflicting_inputs();
  test_confirm_rising_edge();
  test_event_and_exit_require_new_confirm();
  test_holding_confirm_before_event_never_auto_acknowledges();
  test_invalid_updates_do_not_consume_edges();
  test_deterministic_controller_to_viewport_replay();
}
