"""Preflight integration: executed artificial MIPS arithmetic, no original game."""
import struct
import unittest

from tools.audit_gp0_matrix_replay_preflight import analyze, STACK_BASE
from tools.mips_q12_differential import (
    build_nine_product_program, build_nine_dot3_program,
)

BASE = 0x80010000


def exe(words):
    image = struct.pack('<%dI' % len(words), *words)
    header = bytearray(2048)
    header[:8] = b'PS-X EXE'
    struct.pack_into('<II', header, 0x18, BASE, len(image))
    return bytes(header) + image


def probe(words):
    # Synthetic stack holds all zero halfwords. The matrix lives in an
    # independent writable 18-byte region managed by preflight.
    # The preflight stop_pc is an exclusive stop: append a sentinel NOP
    # so the final ninth SH executes before the stop is reached.
    complete = tuple(words) + (0,)
    return analyze(exe(complete), start=BASE, end=BASE+4*len(words),
                   explore=True, max_steps=len(complete)+10,
                   initial_registers={16:STACK_BASE+0x100, 17:STACK_BASE+0x200})


class MatrixOperationSchedulePreflightTests(unittest.TestCase):
    def test_single_signed_mult_schedule_for_all_nine_slots(self):
        result=probe(build_nine_product_program())
        r=result['exploratory_trace']['matrix_operation_schedule']
        self.assertEqual(r['arithmetic_schedule_counts']['single_product_sra12'],9)
        self.assertTrue(r['guest_execution_completed'])
        self.assertFalse(r['original_builder_schedule_identified'])
        self.assertFalse(r['bit_exact_ps1_equivalence_proven'])

    def test_three_products_shifted_after_wrapped_sum(self):
        result=probe(build_nine_dot3_program())
        r=result['exploratory_trace']['matrix_operation_schedule']
        self.assertEqual(r['arithmetic_schedule_counts']['shift_after_three_products'],9)
        self.assertEqual(r['arithmetic_schedule_counts']['shift_each_of_three_products'],0)

    def test_three_products_shifted_individually(self):
        result=probe(build_nine_dot3_program(shift_each=True))
        r=result['exploratory_trace']['matrix_operation_schedule']
        self.assertEqual(r['arithmetic_schedule_counts']['shift_each_of_three_products'],9)
        self.assertEqual(r['arithmetic_schedule_counts']['shift_after_three_products'],0)

    def test_incomplete_trace_must_not_claim_completed_guest_run(self):
        words=build_nine_dot3_program(shift_each=True)
        result=analyze(exe(words),start=BASE,end=BASE+4*(len(words)-1),
                       explore=True,max_steps=8,
                       initial_registers={16:STACK_BASE+0x100,17:STACK_BASE+0x200})
        trace=result['exploratory_trace']
        self.assertEqual(trace['reason'],'step_limit')
        self.assertFalse(trace['matrix_operation_schedule']['guest_execution_completed'])
        self.assertEqual(trace['matrix_operation_schedule']['slots_with_recognized_schedule'],0)

    def test_static_only_has_no_dynamic_operation_schedule(self):
        words=build_nine_product_program()
        result=analyze(exe(words),start=BASE,end=BASE+4*(len(words)-1))
        self.assertNotIn('exploratory_trace',result)

    def test_report_exposes_class_counts_not_coefficients(self):
        r=probe(build_nine_dot3_program())['exploratory_trace']['matrix_operation_schedule']
        self.assertFalse(r['private_values_emitted'])
        self.assertEqual([slot['slot_index'] for slot in r['matrix_slots']],list(range(9)))
        self.assertNotIn('coefficient',str(r))
        self.assertNotIn('0x8011',str(r))

if __name__=='__main__': unittest.main()
