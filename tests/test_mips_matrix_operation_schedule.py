"""Schedule structure checks are against executed synthetic MIPS instructions."""
import struct
import unittest

from tools.mips_q12_differential import (
    build_nine_product_program, build_nine_dot3_program,
    CODE, LEFT, RIGHT, MATRIX,
)
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_matrix_operation_schedule import summarize, classify, Node


def instruction(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def run(words, seed=0):
    image = struct.pack('<%dI' % len(words), *words)
    raw = struct.pack('<27H', *([seed] * 27))
    memory = (MappedMemory().map_region(CODE, image)
              .map_region(LEFT, raw)
              .map_region(RIGHT, raw)
              .map_region(MATRIX, bytes(18), writable=True))
    gpr = [0]*32
    gpr[5], gpr[16], gpr[17] = MATRIX, LEFT, RIGHT
    trace = execute(image, CODE, CODE, memory, gpr,
                    max_steps=len(words)+1)
    return image, trace, summarize(image,CODE,trace,MATRIX)


class OperationScheduleTests(unittest.TestCase):
    def test_nine_direct_signed_products(self):
        image, trace, result = run(build_nine_product_program(), 4096)
        self.assertTrue(trace['completed'])
        self.assertEqual(result['arithmetic_schedule_counts']['single_product_sra12'], 9)
        self.assertEqual(result['slots_with_recognized_schedule'],9)
        self.assertEqual(result['arithmetic_schedule_counts']['unclassified'],0)
        self.assertTrue(all(x['proven_signed_product_terms']==1 for x in result['matrix_slots']))

    def test_nine_dot3_shift_after_sum(self):
        _,trace,r=run(build_nine_dot3_program())
        self.assertTrue(trace['completed'])
        self.assertEqual(r['arithmetic_schedule_counts']['shift_after_three_products'],9)
        self.assertEqual(r['arithmetic_schedule_counts']['shift_each_of_three_products'],0)
        self.assertTrue(all(x['proven_signed_product_terms']==3 for x in r['matrix_slots']))

    def test_nine_dot3_shift_each_product(self):
        _,trace,r=run(build_nine_dot3_program(shift_each=True),65535)
        self.assertTrue(trace['completed'])
        self.assertEqual(r['arithmetic_schedule_counts']['shift_each_of_three_products'],9)
        self.assertEqual(r['arithmetic_schedule_counts']['shift_after_three_products'],0)

    def test_mixed_matrix_slots_and_unwritten(self):
        program=list(build_nine_product_program()[:7]) + [0]
        _,trace,r=run(program)
        self.assertTrue(trace['completed'])
        self.assertEqual(r['arithmetic_schedule_counts']['single_product_sra12'],1)
        self.assertEqual(r['arithmetic_schedule_counts']['not_written'],8)

    def test_sh_overwrite_replaces_old_schedule(self):
        program=list(build_nine_product_program()[:7]) + [instruction(9,0,10,7),instruction(41,5,10,0)]
        _,trace,r=run(program)
        self.assertTrue(trace['completed'])
        self.assertEqual(r['matrix_slots'][0]['schedule'],'unclassified')
        self.assertEqual(r['slots_with_recognized_schedule'],0)

    def test_sw_overwrite_clears_old_sh(self):
        program=list(build_nine_product_program()[:7]) + [instruction(43,5,10,0)]
        _,trace,r=run(program)
        self.assertEqual(r['matrix_slots'][0]['schedule'],'not_written')

    def test_sb_partial_overwrite_clears_old_sh_only(self):
        program=list(build_nine_product_program()[:14]) + [instruction(40,5,10,1)]
        _,trace,r=run(program)
        self.assertEqual(r['matrix_slots'][0]['schedule'],'not_written')
        self.assertEqual(r['matrix_slots'][1]['schedule'],'single_product_sra12')

    def test_truncated_trace_does_not_assert_full_game_completion(self):
        image=struct.pack('<2I',instruction(9,0,10,7),instruction(41,5,10,0))
        memory=MappedMemory().map_region(CODE,image).map_region(MATRIX,bytes(18),writable=True)
        gpr=[0]*32;gpr[5]=MATRIX
        trace=execute(image,CODE,CODE,memory,gpr,max_steps=1)
        report=summarize(image,CODE,trace,MATRIX)
        self.assertFalse(report['guest_execution_completed'])
        self.assertEqual(report['arithmetic_schedule_counts']['not_written'],9)

    def test_store_delay_reads_old_value(self):
        program=list(build_nine_product_program()[:6]) + [instruction(33,16,10,0),instruction(41,5,10,0)]
        _,trace,r=run(program)
        self.assertTrue(trace['completed'])
        # SH in the load-delay slot sees the prior SRA result.
        self.assertEqual(r['matrix_slots'][0]['schedule'],'single_product_sra12')

    def test_trapping_add_not_confused_with_addu_schedule(self):
        program=list(build_nine_dot3_program())
        # Replace all ADDU accumulator opcodes with ADD. The synthetic
        # zero operands avoid overflow, but the opcode schedule differs.
        program=[(word & ~63) | 32 if (word >> 26 == 0 and word & 63 == 33
                    and (word >> 21) & 31 == 11) else word for word in program]
        _,trace,r=run(program)
        self.assertTrue(trace['completed'])
        self.assertEqual(r['arithmetic_schedule_counts']['shift_after_three_products'],0)
        self.assertEqual(r['arithmetic_schedule_counts']['unclassified'],9)

    def test_unsigned_mult_not_confused_with_signed(self):
        program=list(build_nine_product_program()[:7]);program[3]=(program[3]&~63)|25
        _,trace,r=run(program)
        self.assertEqual(r['matrix_slots'][0]['schedule'],'unclassified')

    def test_mflo_without_mult_cannot_prove_product_schedule(self):
        image,trace,r=run([0x00005012,0x000A5303,instruction(41,5,10,0)])
        self.assertEqual(r['matrix_slots'][0]['schedule'],'unclassified')

    def test_absent_executed_memory_event_rejected(self):
        image,trace,r=run(build_nine_product_program()[:7])
        corrupted={**trace,'load_accesses':()}
        with self.assertRaises(ValueError):
            summarize(image,CODE,corrupted,MATRIX)

    def test_extra_store_event_rejected(self):
        image,trace,r=run([0])
        with self.assertRaises(ValueError):
            summarize(image,CODE,{**trace,'store_addresses':(MATRIX,)},MATRIX)

    def test_input_validation(self):
        image,trace,r=run([0])
        with self.assertRaises(ValueError):
            summarize(image,CODE,trace,MATRIX+1)
        with self.assertRaises(ValueError):
            summarize(image,CODE,trace,MATRIX,matrix_slots=0)

    def test_no_guest_addresses_or_literals_in_report(self):
        _,trace,r=run(build_nine_product_program())
        self.assertFalse(r['bit_exact_ps1_equivalence_proven'])
        self.assertFalse(r['original_builder_schedule_identified'])
        self.assertFalse(r['private_values_emitted'])
        self.assertNotIn('0x80100200',str(r))
        self.assertNotIn('address',str(r))

    def test_node_expression_fail_closed(self):
        self.assertEqual(classify(Node('sra12',(Node('other'),)))[0],'unclassified')
        self.assertEqual(classify(None),('not_written',0))

if __name__=='__main__':
    unittest.main()
