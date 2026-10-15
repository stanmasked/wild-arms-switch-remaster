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

# Integrated RTPS depth cue / IR0 host reference.
add_executable(wa_gte_rtps_ir0_reference_tests tests/test_gte_rtps_ir0_reference.cpp)
target_include_directories(wa_gte_rtps_ir0_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtps_ir0_reference_tests COMMAND wa_gte_rtps_ir0_reference_tests)

# External PS1 GTE snapshot comparison: no hardware fixture bundled.
add_executable(wa_gte_reference_runner tests/gte_reference_runner.cpp)
target_include_directories(wa_gte_reference_runner PRIVATE include)
find_package(Python3 COMPONENTS Interpreter REQUIRED)
add_test(NAME wa_gte_external_fixture_contract
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_external_gte_fixture.py)
set_tests_properties(wa_gte_external_fixture_contract PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Guard against mislabeling ps1-tests summary logs as GTE reference vectors.
add_test(NAME wa_gte_external_log_inspector
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_gte_log_inspector.py)
set_tests_properties(wa_gte_external_log_inspector PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Strict 64-register ps1-tests gte-fuzz capture importer contract.
add_test(NAME wa_gte_fuzz_rtps_import_contract
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_import_gte_fuzz_rtps.py)
set_tests_properties(wa_gte_fuzz_rtps_import_contract PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Detect malformed and interleaved ps1-tests GTE fuzz register blocks.
add_test(NAME wa_gte_fuzz_strict_contract
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gte_fuzz_strict_contract.py)
set_tests_properties(wa_gte_fuzz_strict_contract PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Verify psx-spx packed matrix, vertex and output register mapping in gte-fuzz logs.
add_test(NAME wa_gte_fuzz_register_mapping
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gte_fuzz_register_mapping.py)
set_tests_properties(wa_gte_fuzz_register_mapping PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Verify C++ reference runner rejects malformed or out-of-range register inputs.
add_test(NAME wa_gte_runner_input_contract
         COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/check_gte_runner_input.py
                 $<TARGET_FILE:wa_gte_reference_runner>)

# Differential screen/IR0 overflow behavior from independent emulator semantics.
add_executable(wa_gte_mac0_wide_intermediate_tests tests/test_gte_mac0_wide_intermediate.cpp)
target_include_directories(wa_gte_mac0_wide_intermediate_tests PRIVATE include)
add_test(NAME wa_gte_mac0_wide_intermediate_tests COMMAND wa_gte_mac0_wide_intermediate_tests)

# Preserve RTPS SXY0..2 and SZ0..3 FIFO state between vertices.
add_executable(wa_gte_rtps_fifo_tests tests/test_gte_rtps_fifo.cpp)
target_include_directories(wa_gte_rtps_fifo_tests PRIVATE include)
add_test(NAME wa_gte_rtps_fifo_tests COMMAND wa_gte_rtps_fifo_tests)

# Triple RTPT reference reusing stateful single-vertex RTPS.
add_executable(wa_gte_rtpt_reference_tests tests/test_gte_rtpt_reference.cpp)
target_include_directories(wa_gte_rtpt_reference_tests PRIVATE include)
add_test(NAME wa_gte_rtpt_reference_tests COMMAND wa_gte_rtpt_reference_tests)

# Oriented NCLIP triangle area and sequential RTPT-to-NCLIP reference.
add_executable(wa_gte_nclip_reference_tests tests/test_gte_nclip_reference.cpp)
target_include_directories(wa_gte_nclip_reference_tests PRIVATE include)
add_test(NAME wa_gte_nclip_reference_tests COMMAND wa_gte_nclip_reference_tests)

# Conservative face classification with explicitly configured winding convention.
add_executable(wa_gte_triangle_classification_tests tests/test_gte_triangle_classification.cpp)
target_include_directories(wa_gte_triangle_classification_tests PRIVATE include)
add_test(NAME wa_gte_triangle_classification_tests COMMAND wa_gte_triangle_classification_tests)

# Reverse-engineered PS-X EXE polygon winding: synthetic opcode tests only.
add_test(NAME wa_original_nclip_winding_audit
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_original_nclip_winding.py)
set_tests_properties(wa_original_nclip_winding_audit PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Static, game-asset-free tests for SWC2 polygon-coordinate writes after NCLIP.
add_test(NAME wa_original_nclip_polygon_writes
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_nclip_polygon_writes.py)
set_tests_properties(wa_original_nclip_polygon_writes PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Static opcode contract for original Wild Arms GPU OT packet linkage.
add_test(NAME wa_original_nclip_ot_packets
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_nclip_ot_packets.py)
set_tests_properties(wa_original_nclip_ot_packets PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
