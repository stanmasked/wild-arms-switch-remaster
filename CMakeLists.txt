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

# Match PS1 GP0 triangle layout candidates against original packet SXY offsets.
add_test(NAME wa_original_gp0_triangle_layouts
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_triangle_layouts.py)
set_tests_properties(wa_original_gp0_triangle_layouts PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Static GP0 first-command-word and opcode-byte preservation analysis.
add_test(NAME wa_original_gp0_opcode_provenance
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_opcode_provenance.py)
set_tests_properties(wa_original_gp0_opcode_provenance PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Independently audit RGB FIFO color stores in original polygon command packets.
add_test(NAME wa_original_gp0_color_fifo
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_color_fifo.py)
set_tests_properties(wa_original_gp0_color_fifo PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Detect direct stores into FT3/GT3 UV/CLUT/TPAGE words in original NCLIP paths.
add_test(NAME wa_original_gp0_texture_fields
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_texture_fields.py)
set_tests_properties(wa_original_gp0_texture_fields PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Static packet pointer alias and fixed stride analysis for original Wild Arms.
add_test(NAME wa_original_gp0_packet_stride
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_packet_stride.py)
set_tests_properties(wa_original_gp0_packet_stride PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Static direct JAL packet-renderer call sites and a0 source provenance.
add_test(NAME wa_original_gp0_callers
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_callers.py)
set_tests_properties(wa_original_gp0_callers PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Original Wild Arms structure +16 pointer arithmetic (static MIPS pattern contract).
add_test(NAME wa_original_gp0_packet_field16
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_packet_field16.py)
set_tests_properties(wa_original_gp0_packet_field16 PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# PS-X original GPU packet cursor: base+12 initialization and four-byte steps.
add_test(NAME wa_original_gp0_cursor_lifecycle
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_cursor_lifecycle.py)
set_tests_properties(wa_original_gp0_cursor_lifecycle PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Trace direct JAL entry and a0 argument sources for polygon cursor setup.
add_test(NAME wa_original_gp0_structure_callers
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_structure_callers.py)
set_tests_properties(wa_original_gp0_structure_callers PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Recover original Wild Arms polygon structure r20/r22 root pointer origins.
add_test(NAME wa_original_gp0_root_registers
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_root_registers.py)
set_tests_properties(wa_original_gp0_root_registers PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Original polygon root globals and JAL delay-slot a3 stack argument audit.
add_test(NAME wa_original_gp0_global_writes_a3
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_global_writes_a3.py)
set_tests_properties(wa_original_gp0_global_writes_a3 PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Original polygon setup/renderer stack object handoff through a2 and a3.
add_test(NAME wa_original_gp0_stack_handoff
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_stack_handoff.py)
set_tests_properties(wa_original_gp0_stack_handoff PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Original polygon stack helper GTE MVMVA output to a1[0..8].
add_test(NAME wa_original_gp0_helper_mvmva
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_helper_mvmva.py)
set_tests_properties(wa_original_gp0_helper_mvmva PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Decode original GTE MVMVA control bits and verify the original opcode word.
add_test(NAME wa_original_gp0_mvmva_control
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_mvmva_control.py)
set_tests_properties(wa_original_gp0_mvmva_control PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Verify original rotation matrix load from caller stack to GTE control registers.
add_test(NAME wa_original_gp0_rotation_matrix_load
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_rotation_matrix_load.py)
set_tests_properties(wa_original_gp0_rotation_matrix_load PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Original rotation matrix constructor writes nine signed halfword slots.
add_test(NAME wa_original_gp0_rotation_matrix_builder
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_rotation_matrix_builder.py)
set_tests_properties(wa_original_gp0_rotation_matrix_builder PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Verify original packed fixed-point trigonometric table and six indexed reads.
add_test(NAME wa_original_gp0_trig_table
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_trig_table.py)
set_tests_properties(wa_original_gp0_trig_table PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Decode multiply, HI/LO and signed shifts in the original matrix constructor.
add_test(NAME wa_original_gp0_matrix_arithmetic
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_arithmetic.py)
set_tests_properties(wa_original_gp0_matrix_arithmetic PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Conservative intra-block lookup-to-matrix provenance, synthetic opcode fixtures.
add_test(NAME wa_original_gp0_matrix_provenance
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_provenance.py)
set_tests_properties(wa_original_gp0_matrix_provenance PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Conservative direct MIPS branch edges and delay-slot CFG contracts.
add_test(NAME wa_original_gp0_matrix_cfg
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_cfg.py)
set_tests_properties(wa_original_gp0_matrix_cfg PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Fixed-point may-source join analysis over supported MIPS CFG edges.
add_test(NAME wa_original_gp0_matrix_cfg_join
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_cfg_join.py)
set_tests_properties(wa_original_gp0_matrix_cfg_join PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Restricted context-sensitive MIPS delay-slot CFG contract.
add_test(NAME wa_original_gp0_matrix_context_cfg
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_context_cfg.py)
set_tests_properties(wa_original_gp0_matrix_context_cfg PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Context-labelled MIPS CFG with conservative GPR and HI/LO provenance.
add_test(NAME wa_original_gp0_matrix_context_sources
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_context_sources.py)
set_tests_properties(wa_original_gp0_matrix_context_sources PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Standalone bit-accurate MIPS arithmetic primitives.
add_test(NAME wa_mips_fixed32
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_fixed32.py)
set_tests_properties(wa_mips_fixed32 PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Concrete subset of PS1 MIPS integer instruction execution.
add_test(NAME wa_mips_integer_step
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_integer_step.py)
set_tests_properties(wa_mips_integer_step PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Bounded concrete integer instruction sequences (host-only).
add_test(NAME wa_mips_integer_sequence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_integer_sequence.py)
set_tests_properties(wa_mips_integer_sequence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Linear bounded memory access and one-instruction MIPS load delay.
add_test(NAME wa_mips_memory_sequence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_memory_sequence.py)
set_tests_properties(wa_mips_memory_sequence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Caller-owned Q12 trig-table mapping and integer reconstruction.
add_test(NAME wa_mips_trig_memory
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_trig_memory.py)
set_tests_properties(wa_mips_trig_memory PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Separate protected trig table and nine writable PS1 matrix coefficient slots.
add_test(NAME wa_mips_matrix_memory
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_matrix_memory.py)
set_tests_properties(wa_mips_matrix_memory PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Executable, bounded MIPS branches and delay-slot behavior (synthetic input).
add_test(NAME wa_mips_control_flow
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_control_flow.py)
set_tests_properties(wa_mips_control_flow PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Private PS-X executable matrix-replay coverage and synthetic probe safety.
add_test(NAME wa_gp0_matrix_replay_preflight
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_replay_preflight.py)
set_tests_properties(wa_gp0_matrix_replay_preflight PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# MIPS register input dependencies discovered along completed concrete paths.
add_test(NAME wa_mips_entry_dependencies
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_entry_dependencies.py)
set_tests_properties(wa_mips_entry_dependencies PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Synthetic PS1 caller-register sensitivity and matrix output comparisons.
add_test(NAME wa_mips_input_sensitivity
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_input_sensitivity.py)
set_tests_properties(wa_mips_input_sensitivity PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Caller/callee register readiness across JAL and its load-delay slot.
add_test(NAME wa_mips_call_boundary
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_call_boundary.py)
set_tests_properties(wa_mips_call_boundary PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Conservative caller-side argument source classification before matrix JAL.
add_test(NAME wa_mips_caller_sources
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_caller_sources.py)
set_tests_properties(wa_mips_caller_sources PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Conservative multi-path MIPS caller provenance through branch delay slots.
add_test(NAME wa_mips_caller_cfg_sources
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_caller_cfg_sources.py)
set_tests_properties(wa_mips_caller_cfg_sources PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Match bounded synthetic MIPS replay traces to conservative caller CFG paths.
add_test(NAME wa_mips_cfg_probe_path
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_cfg_probe_path.py)
set_tests_properties(wa_mips_cfg_probe_path PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Integrated JAL/caller CFG probing, including full-window replay safety.
add_test(NAME wa_gp0_cfg_runtime_correlation
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_cfg_runtime_correlation.py)
set_tests_properties(wa_gp0_cfg_runtime_correlation PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Actual successful MIPS loads and privacy-safe trig/stack read profiles.
add_test(NAME wa_mips_load_access_profile
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_load_access_profile.py)
set_tests_properties(wa_mips_load_access_profile PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Synthetic PS-X EXE Q12 lookup preflight integration.
add_test(NAME wa_gp0_matrix_load_profile
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_load_profile.py)
set_tests_properties(wa_gp0_matrix_load_profile PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Shadow provenance for completed MIPS Q12 table-address computations.
add_test(NAME wa_mips_trig_index_provenance
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_trig_index_provenance.py)
set_tests_properties(wa_mips_trig_index_provenance PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Synthetic PS-X EXE preflight integration for angle-address chains.
add_test(NAME wa_gp0_trig_index_provenance
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_trig_index_provenance.py)
set_tests_properties(wa_gp0_trig_index_provenance PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Synthetic Q12 data-dependence through MIPS ALU/HI/LO to final matrix SH slots.
add_test(NAME wa_mips_matrix_value_lineage
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_matrix_value_lineage.py)
set_tests_properties(wa_mips_matrix_value_lineage PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Private EXE preflight integration with artificial Q12 matrices.
add_test(NAME wa_gp0_matrix_value_lineage
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_value_lineage.py)
set_tests_properties(wa_gp0_matrix_value_lineage PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Independent, host-only fixed-point oracle for explicit synthetic PS1 Q12 schedules.
add_test(NAME wa_mips_q12_arithmetic_reference
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_q12_arithmetic_reference.py)
set_tests_properties(wa_mips_q12_arithmetic_reference PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Full MIPS LH/MULT/MFLO/SRA/SH numeric differential checks for nine matrix slots.
add_test(NAME wa_mips_q12_differential
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_q12_differential.py)
set_tests_properties(wa_mips_q12_differential PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Safe deterministic summary CLI: no original game executable or assets needed.
add_test(NAME wa_audit_mips_q12_differential
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_audit_mips_q12_differential.py)
set_tests_properties(wa_audit_mips_q12_differential PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Classify executed MULT/MFLO/SRA/ADDU ordering at nine matrix SH outputs.
add_test(NAME wa_mips_matrix_operation_schedule
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_matrix_operation_schedule.py)
set_tests_properties(wa_mips_matrix_operation_schedule PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Synthetic PS-X EXE integration for all nine concrete coefficient slots.
add_test(NAME wa_gp0_matrix_operation_schedule
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_matrix_operation_schedule.py)
set_tests_properties(wa_gp0_matrix_operation_schedule PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 208: static original builder opcode and local arithmetic motif evidence.
add_test(NAME wa_mips_builder_opcode_evidence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_builder_opcode_evidence.py)
set_tests_properties(wa_mips_builder_opcode_evidence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 208: synthetic EXE integration, including known Wild Arms code addresses.
add_test(NAME wa_gp0_builder_opcode_evidence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_builder_opcode_evidence.py)
set_tests_properties(wa_gp0_builder_opcode_evidence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 209: count only successful executed matrix SH sites and validated Q12 reads.
add_test(NAME wa_mips_builder_execution_evidence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_builder_execution_evidence.py)
set_tests_properties(wa_mips_builder_execution_evidence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 209: compare static and executed sites inside synthetic PS-X EXE.
add_test(NAME wa_gp0_builder_execution_evidence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_builder_execution_evidence.py)
set_tests_properties(wa_gp0_builder_execution_evidence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 210: verify the synthetic caller -> six Q12 loads -> nine matrix SH -> JR return chain.
add_test(NAME wa_mips_builder_integrity_gate
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_builder_integrity_gate.py)
set_tests_properties(wa_mips_builder_integrity_gate PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 210: synthetic whole-path PS-X EXE with known Wild Arms guest code sites.
add_test(NAME wa_gp0_builder_integrity_gate
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_gp0_builder_integrity_gate.py)
set_tests_properties(wa_gp0_builder_integrity_gate PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 211: compare privately supplied PS1 reference coefficients to a bounded MIPS replay.
add_test(NAME wa_mips_ps1_matrix_reference
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_ps1_matrix_reference.py)
set_tests_properties(wa_mips_ps1_matrix_reference PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 211: reference verifier command-line validation and safe failure codes.
add_test(NAME wa_audit_ps1_matrix_reference
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_audit_ps1_matrix_reference.py)
set_tests_properties(wa_audit_ps1_matrix_reference PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 212: package private before/after debugger captures into stage-211 references.
add_test(NAME wa_mips_ps1_capture_pack
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_ps1_capture_pack.py)
set_tests_properties(wa_mips_ps1_capture_pack PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 212: safe CLI outputs, no private stdout, and restrictive JSON permissions.
add_test(NAME wa_audit_ps1_capture_pack
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_audit_ps1_capture_pack.py)
set_tests_properties(wa_audit_ps1_capture_pack PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 213: captured R3000A pending-load hazards and branch-delay state.
add_test(NAME wa_mips_initial_pipeline
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_initial_pipeline.py)
set_tests_properties(wa_mips_initial_pipeline PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 213: strict external PS1 capture pipeline declarations.
add_test(NAME wa_ps1_pipeline_capture
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_pipeline_capture.py)
set_tests_properties(wa_ps1_pipeline_capture PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 213: consistency across code execution and dependency shadows.
add_test(NAME wa_mips_load_pipeline_shadow
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_load_pipeline_shadow.py)
set_tests_properties(wa_mips_load_pipeline_shadow PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 214: completed JR $ra transfer, return delay-slot and drained pipeline.
add_test(NAME wa_mips_return_boundary
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_return_boundary.py)
set_tests_properties(wa_mips_return_boundary PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 214: opt-in strict nine-coefficient PS1 snapshot return verification.
add_test(NAME wa_ps1_reference_return_boundary
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_reference_return_boundary.py)
set_tests_properties(wa_ps1_reference_return_boundary PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 215: private 32-register, HI/LO and pending-load post-return comparison.
add_test(NAME wa_mips_final_cpu_state
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_final_cpu_state.py)
set_tests_properties(wa_mips_final_cpu_state PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 215: stage-211 reference and stage-212 capture pack integration.
add_test(NAME wa_ps1_final_cpu_capture
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_final_cpu_capture.py)
set_tests_properties(wa_ps1_final_cpu_capture PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 216: private full-after-RAM block digests and outside-matrix side effects.
add_test(NAME wa_mips_final_memory_state
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_final_memory_state.py)
set_tests_properties(wa_mips_final_memory_state PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 216: snapshot packaging and strict guest memory comparison with synthetic PS-X EXE.
add_test(NAME wa_ps1_final_memory_capture
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_final_memory_capture.py)
set_tests_properties(wa_ps1_final_memory_capture PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 217: record and compare successful SB/SH/SW event order.
add_test(NAME wa_mips_store_event_sequence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_store_event_sequence.py)
set_tests_properties(wa_mips_store_event_sequence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 217: private debugger write-trace integration and CLI validation.
add_test(NAME wa_ps1_store_sequence_capture
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_store_sequence_capture.py)
set_tests_properties(wa_ps1_store_sequence_capture PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 218: verify exact values written by every successful SB/SH/SW.
add_test(NAME wa_mips_store_value_sequence
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_mips_store_value_sequence.py)
set_tests_properties(wa_mips_store_value_sequence PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Stage 218: independent private PS1 debugger store-value events and CLI.
add_test(NAME wa_ps1_store_value_capture
         COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -p test_ps1_store_value_capture.py)
set_tests_properties(wa_ps1_store_value_capture PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
