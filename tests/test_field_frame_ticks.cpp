#include "field_frame_ticks.hpp"

#include <cstdint>
#include <cstdlib>
#include <limits>

namespace {
using namespace wa::field;

void require(bool valid) {
  if (!valid) std::abort();
}

void test_60hz_frames_preserve_fractional_milliseconds() {
  FrameTickClock clock = make_frame_tick_clock(19200000, 0);
  std::uint64_t tick = 0;
  std::uint32_t total = 0;
  int frame16 = 0;
  int frame17 = 0;
  for (int frame = 0; frame < 60; ++frame) {
    tick += 320000; // Exactly 1/60th of a 19.2MHz second.
    const FrameTickDelta d = advance_frame_ticks(clock, tick);
    require(d.status == FrameTickStatus::Ready);
    require(d.milliseconds == 16 || d.milliseconds == 17);
    frame16 += d.milliseconds == 16;
    frame17 += d.milliseconds == 17;
    total += d.milliseconds;
  }
  require(frame16 == 20 && frame17 == 40);
  require(total == 1000 && clock.fractional == 0);
  require(advance_frame_ticks(clock, tick).milliseconds == 0);
  require(clock.fractional == 0);
}

void test_partition_invariance_with_noninteger_frequency() {
  constexpr std::uint64_t freq = 1000003;
  FrameTickClock a = make_frame_tick_clock(freq, 123);
  FrameTickClock b = make_frame_tick_clock(freq, 123);
  std::uint64_t tick = 123;
  std::uint32_t partition_sum = 0;
  for (int i = 0; i < 7; ++i) {
    tick += 123456;
    const auto part = advance_frame_ticks(b, tick);
    require(part.status == FrameTickStatus::Ready);
    partition_sum += part.milliseconds;
  }
  const auto whole = advance_frame_ticks(a, tick);
  require(whole.status == FrameTickStatus::Ready);
  require(partition_sum == whole.milliseconds &&
          a.fractional == b.fractional);
}

void test_long_pause_drops_time_and_partial_millisecond() {
  FrameTickClock clock = make_frame_tick_clock(19200000, 0);
  require(advance_frame_ticks(clock, 320000).milliseconds == 16);
  require(clock.fractional != 0);
  const auto gap = advance_frame_ticks(clock, 19200000 * 6);
  require(gap.status == FrameTickStatus::SkippedPause &&
          gap.milliseconds == 0 && clock.fractional == 0);
  require(clock.previous_tick == 19200000u * 6);
  const auto resumed =
      advance_frame_ticks(clock, 19200000 * 6 + 192000);
  require(resumed.status == FrameTickStatus::Ready &&
          resumed.milliseconds == 10);
  require(clock.fractional == 0);
}

void test_counter_reset_and_64bit_boundaries() {
  const auto maximum = std::numeric_limits<std::uint64_t>::max();
  FrameTickClock clock = make_frame_tick_clock(1000, maximum - 100);
  require(advance_frame_ticks(clock, maximum).milliseconds == 100);
  const auto reset = advance_frame_ticks(clock, 5);
  require(reset.status == FrameTickStatus::ResetCounter &&
          reset.milliseconds == 0);
  require(clock.previous_tick == 5 && clock.fractional == 0);
  require(advance_frame_ticks(clock, 1005).milliseconds == 1000);
}

void test_invalid_frequency_and_fraction_are_rejected_without_mutation() {
  FrameTickClock clock = make_frame_tick_clock(999, 42);
  require(!clock.valid());
  require(advance_frame_ticks(clock, 100).status ==
          FrameTickStatus::InvalidClock);
  require(clock.previous_tick == 42);
  clock.frequency_hz = kMaximumFrameTickFrequencyHz + 1;
  require(advance_frame_ticks(clock, 100).status ==
          FrameTickStatus::InvalidClock);
  require(clock.previous_tick == 42);
  clock.frequency_hz = 1000;
  clock.fractional = 1000;
  require(advance_frame_ticks(clock, 100).status ==
          FrameTickStatus::InvalidClock);
  require(clock.previous_tick == 42 && clock.fractional == 1000);
}

void test_single_second_and_zero_elapsed() {
  FrameTickClock clock = make_frame_tick_clock(1000000, 500);
  auto d = advance_frame_ticks(clock, 500);
  require(d.status == FrameTickStatus::Ready && d.milliseconds == 0);
  d = advance_frame_ticks(clock, 1000500);
  require(d.status == FrameTickStatus::Ready && d.milliseconds == 1000);
  d = advance_frame_ticks(clock, 3000500);
  require(d.status == FrameTickStatus::SkippedPause &&
          d.milliseconds == 0);
}

}  // namespace
int main() {
  test_60hz_frames_preserve_fractional_milliseconds();
  test_partition_invariance_with_noninteger_frequency();
  test_long_pause_drops_time_and_partial_millisecond();
  test_counter_reset_and_64bit_boundaries();
  test_invalid_frequency_and_fraction_are_rejected_without_mutation();
  test_single_second_and_zero_elapsed();
}
