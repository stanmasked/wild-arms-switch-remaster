cmake_minimum_required(VERSION 3.16)
project(wild_arms_switch LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_library(wa_core src/core.cpp)
target_include_directories(wa_core PUBLIC include)
enable_testing()
add_executable(wa_core_tests tests/test_core.cpp)
target_link_libraries(wa_core_tests PRIVATE wa_core)
add_test(NAME wa_core_tests COMMAND wa_core_tests)

# Host-verified groundwork for an eventual native PS1 GTE RTPS implementation.
add_executable(wa_gte_math_tests tests/test_gte_math.cpp)
target_include_directories(wa_gte_math_tests PRIVATE include)
add_test(NAME wa_gte_math_tests COMMAND wa_gte_math_tests)

# Host reference tests for fixed-point rotate/translate (not full GTE RTPS).
add_executable(wa_gte_transform_tests tests/test_gte_transform.cpp)
target_include_directories(wa_gte_transform_tests PRIVATE include)
add_test(NAME wa_gte_transform_tests COMMAND wa_gte_transform_tests)

# Host-only integer projection reference (not hardware-accurate GTE).
add_executable(wa_gte_projection_tests tests/test_gte_projection.cpp)
target_include_directories(wa_gte_projection_tests PRIVATE include)
add_test(NAME wa_gte_projection_tests COMMAND wa_gte_projection_tests)

add_executable(wa_gte_rtps_reference_tests tests/test_gte_rtps_reference.cpp)
target_include_directories(wa_gte_rtps_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_reference_tests COMMAND wa_gte_rtps_reference_tests)

# Documented PS1 GTE UNR divide algorithm tests (standalone).
add_executable(wa_gte_unr_division_tests tests/test_gte_unr_division.cpp)
target_include_directories(wa_gte_unr_division_tests PRIVATE include)
add_test(NAME wa_gte_unr_division_tests COMMAND wa_gte_unr_division_tests)

# Compare hardware-inspired UNR divide with the earlier host projection model.
add_executable(wa_gte_projection_unr_tests tests/test_gte_projection_unr.cpp)
target_include_directories(wa_gte_projection_unr_tests PRIVATE include)
add_test(NAME wa_gte_projection_unr_tests COMMAND wa_gte_projection_unr_tests)

# Composite host RTPS using UNR perspective; not full PlayStation GTE.
add_executable(wa_gte_rtps_unr_reference_tests tests/test_gte_rtps_unr_reference.cpp)
target_include_directories(wa_gte_rtps_unr_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_unr_reference_tests COMMAND wa_gte_rtps_unr_reference_tests)

# Fixed-point GTE OFX/OFY screen stage and MAC0 diagnostic flags.
add_executable(wa_gte_screen_stage_tests tests/test_gte_screen_stage.cpp)
target_include_directories(wa_gte_screen_stage_tests PRIVATE include)
add_test(NAME wa_gte_screen_stage_tests COMMAND wa_gte_screen_stage_tests)

# Composite UNR RTPS with fractional screen-offset stage.
add_executable(wa_gte_rtps_screen_reference_tests tests/test_gte_rtps_screen_reference.cpp)
target_include_directories(wa_gte_rtps_screen_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_screen_reference_tests COMMAND wa_gte_rtps_screen_reference_tests)

# Standalone GTE MAC1..3 accumulator boundaries, IR saturation and FLAG.
add_executable(wa_gte_mac_stage_tests tests/test_gte_mac_stage.cpp)
target_include_directories(wa_gte_mac_stage_tests PRIVATE include)
add_test(NAME wa_gte_mac_stage_tests COMMAND wa_gte_mac_stage_tests)

# Experimental MAC/IR/FLAG RTPS composite (not hardware bit-exact).
add_executable(wa_gte_rtps_mac_reference_tests tests/test_gte_rtps_mac_reference.cpp)
target_include_directories(wa_gte_rtps_mac_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_mac_reference_tests COMMAND wa_gte_rtps_mac_reference_tests)

# Per-step signed 44-bit accumulator model and overflow regression tests.
add_executable(wa_gte_mac44_accumulate_tests tests/test_gte_mac44_accumulate.cpp)
target_include_directories(wa_gte_mac44_accumulate_tests PRIVATE include)
add_test(NAME wa_gte_mac44_accumulate_tests COMMAND wa_gte_mac44_accumulate_tests)

# MAC44 step-by-step RTPS reference and transient overflow comparisons.
add_executable(wa_gte_rtps_mac44_reference_tests tests/test_gte_rtps_mac44_reference.cpp)
target_include_directories(wa_gte_rtps_mac44_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_mac44_reference_tests COMMAND wa_gte_rtps_mac44_reference_tests)

# Isolated RTPS IR3 saturation flag versus SZ3 depth rules (sf/lm).
add_executable(wa_gte_rtps_depth_stage_tests tests/test_gte_rtps_depth_stage.cpp)
target_include_directories(wa_gte_rtps_depth_stage_tests PRIVATE include)
add_test(NAME wa_gte_rtps_depth_stage_tests COMMAND wa_gte_rtps_depth_stage_tests)

# Combined per-step MAC44 and special IR3/SZ3 test.
add_executable(wa_gte_rtps_mac44_depth_reference_tests tests/test_gte_rtps_mac44_depth_reference.cpp)
target_include_directories(wa_gte_rtps_mac44_depth_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_mac44_depth_reference_tests COMMAND wa_gte_rtps_mac44_depth_reference_tests)

# Standalone RTPS depth cue (MAC0/DQA/DQB -> IR0), partial FLAG.
add_executable(wa_gte_depth_cue_stage_tests tests/test_gte_depth_cue_stage.cpp)
target_include_directories(wa_gte_depth_cue_stage_tests PRIVATE include)
add_test(NAME wa_gte_depth_cue_stage_tests COMMAND wa_gte_depth_cue_stage_tests)
