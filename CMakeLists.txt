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
