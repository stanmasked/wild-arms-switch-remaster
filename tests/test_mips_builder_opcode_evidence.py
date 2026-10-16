"""All sequences synthetic: static opcode reconnaissance never proves PS1 gameplay."""
import struct
import unittest
from tools.mips_builder_opcode_evidence import inspect
from tools.mips_q12_differential import (
    build_nine_product_program, build_nine_dot3_program,
)
from tools.audit_gp0_rotation_matrix_builder import BUILDER, RETURN
from tools.audit_gp0_trig_table import TABLE_LOAD_PCS

BASE = 0x80010000


def special(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)


def check(words, *, known_lookup_pcs=()):
    image = struct.pack('<%dI' % len(words), *words)
    return inspect(image, BASE, BASE, BASE + len(image) - 4,
                   known_lookup_pcs=known_lookup_pcs)


class BuilderOpcodeEvidenceTests(unittest.TestCase):
    def test_nine_single_products_are_candidate_shapes_only(self):
        report = check(build_nine_product_program())
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'], 9)
        self.assertTrue(report['all_nine_slots_statically_referenced'])
        self.assertEqual(report['static_matrix_sh_slot_indices'], list(range(9)))
        self.assertEqual(report['opcode_counts']['mult'], 9)
        self.assertEqual(report['opcode_counts']['mflo'], 9)
        self.assertEqual(report['opcode_counts']['sra12'], 9)
        self.assertEqual(report['opcode_counts']['sh'], 9)
        self.assertFalse(report['original_builder_schedule_identified'])

    def test_shift_after_three_products(self):
        report = check(build_nine_dot3_program())
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['shift_after_three_products'], 9)
        self.assertEqual(report['opcode_counts']['mult'], 27)
        self.assertEqual(report['opcode_counts']['sra12'], 9)
        self.assertEqual(report['opcode_counts']['addu'], 27)

    def test_shift_each_product(self):
        report = check(build_nine_dot3_program(shift_each=True))
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['shift_each_of_three_products'], 9)
        self.assertEqual(report['opcode_counts']['sra12'], 27)

    def test_trapping_add_not_silently_called_addu(self):
        code = list(build_nine_dot3_program())
        code = [(w & ~63)|32 if w >> 26 == 0 and (w & 63) == 33 and
                (w >> 21) & 31 == 11 else w for w in code]
        report = check(code)
        self.assertEqual(report['opcode_counts']['add'], 27)
        self.assertEqual(report['opcode_counts']['addu'], 0)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['shift_after_three_products'], 0)

    def test_unsigned_mult_not_classified_signed(self):
        words = list(build_nine_product_program()[:7])
        words[3] = (words[3] & ~63) | 25
        report = check(words)
        self.assertEqual(report['opcode_counts']['multu'], 1)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'], 0)

    def test_unmodeled_coprocessor_opcode_invalidates_local_schedule(self):
        code = list(build_nine_product_program()[:6])
        code += [18<<26, ins(41,5,10,0)]  # Synthetic COP2 in between.
        report = check(code)
        self.assertEqual(report['unsupported_provenance_barriers'],1)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'],0)

    def test_control_barrier_invalidates_pre_branch_provenance(self):
        words = list(build_nine_product_program()[:5]) + [ins(4,4,6,1),0] + [
            special(3,rt=10,rd=10,sa=12), ins(41,5,10,0)]
        report = check(words)
        self.assertEqual(report['control_flow_barriers'],1)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'],0)
        self.assertEqual(report['static_matrix_sh_slot_indices'],[0])

    def test_branch_delay_slot_sh_is_not_claimed_as_candidate(self):
        code = list(build_nine_product_program()[:6]) + [ins(4,4,6,1),
                                                       ins(41,5,10,0)]
        report = check(code)
        self.assertEqual(report['static_matrix_sh_sites'],0)
        self.assertEqual(report['straight_line_candidate_slot_indices'],[])
        self.assertEqual(report['opcode_counts']['sh'],1)
        self.assertEqual(report['delay_slot_matrix_sh_sites'],1)

    def test_single_product_multu_same_shape_still_distinct(self):
        code = list(build_nine_product_program()[:7])
        code[3] |= 1  # MULTU
        report = check(code)
        self.assertEqual(report['straight_line_candidate_slot_indices'],[])
        self.assertEqual(report['static_matrix_sh_slot_indices'],[0])

    def test_duplicate_sh_sites_not_assumed_final(self):
        words = list(build_nine_product_program()[:7])
        words += [ins(9,0,10,1),ins(41,5,10,0)]
        report = check(words)
        self.assertEqual(report['static_matrix_sh_duplicate_sites'],1)
        self.assertEqual(report['static_matrix_sh_sites'],2)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'],1)

    def test_wrong_sh_base_or_unaligned_slot_is_other(self):
        code=[ins(41,29,10,0),ins(41,5,10,1),ins(41,5,10,18)]
        report = check(code)
        self.assertEqual(report['static_matrix_sh_sites'],0)
        self.assertEqual(report['other_sh_sites'],3)

    def test_lookup_site_opcode_not_assumed_actual_trig_read(self):
        report=check([ins(35,8,9,0),ins(35,8,9,0),0],
                     known_lookup_pcs=(BASE,BASE+4,BASE+8))
        self.assertEqual(report['known_lookup_sites_in_range'],3)
        self.assertEqual(report['known_lookup_sites_with_lw_opcode'],2)
        self.assertFalse(report['static_words_are_executed'])

    def test_return_jr_ra_with_delay_slot_available(self):
        code=[0, special(8,rs=31),0]
        image=struct.pack('<3I',*code)
        report=inspect(image,BASE,BASE,BASE+4,known_lookup_pcs=())
        self.assertTrue(report['return_site_encodes_jr_ra'])
        self.assertTrue(report['return_delay_slot_word_available'])

    def test_return_delay_slot_ninth_sh_is_tracked_separately(self):
        words = [ins(41,5,10,i*2) for i in range(8)]
        words += [special(8,rs=31), ins(41,5,10,16)]
        image=struct.pack('<%dI'%len(words),*words)
        report=inspect(image,BASE,BASE,BASE+4*(len(words)-2),known_lookup_pcs=())
        self.assertFalse(report['all_nine_slots_statically_referenced'])
        self.assertTrue(report['all_nine_slots_referenced_including_return_delay_slot'])
        self.assertEqual(report['return_delay_slot_opcode_kind'],'sh')
        self.assertEqual(report['return_delay_slot_matrix_sh_slot_index'],8)
        self.assertEqual(report['static_matrix_sh_slot_indices'],list(range(8)))

    def test_return_delay_slot_missing_is_explicit(self):
        report=check([0,special(8,rs=31)])
        self.assertTrue(report['return_site_encodes_jr_ra'])
        self.assertFalse(report['return_delay_slot_word_available'])

    def test_real_builder_address_window_without_game_bytes(self):
        # Real address constants but completely artificial machine code.
        length=(RETURN-BUILDER)//4+2
        words=[0]*length
        for pc in TABLE_LOAD_PCS:
            words[(pc-BUILDER)//4]=ins(35,8,9,0)
        words[(RETURN-BUILDER)//4]=special(8,rs=31)
        image=struct.pack('<%dI'%len(words),*words)
        report=inspect(image,BUILDER,BUILDER,RETURN)
        self.assertEqual(report['instruction_count'],(RETURN-BUILDER)//4+1)
        self.assertEqual(report['known_lookup_sites_in_range'],6)
        self.assertEqual(report['known_lookup_sites_with_lw_opcode'],6)
        self.assertTrue(report['return_site_encodes_jr_ra'])
        self.assertTrue(report['return_delay_slot_word_available'])
        self.assertFalse(report['original_builder_schedule_identified'])

    def test_invalid_ranges_and_args_fail_closed(self):
        image=struct.pack('<2I',0,0)
        for start,end in ((BASE-4,BASE),(BASE,BASE+8),(BASE+4,BASE),
                          (BASE+1,BASE+4)):
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):
                inspect(image,BASE,start,end)
        with self.assertRaises(ValueError):
            inspect(image,BASE,BASE,BASE+4,slot_count=0)
        with self.assertRaises(ValueError):
            inspect(image,BASE,BASE,BASE+4,known_lookup_pcs=(-1,))

    def test_no_private_words_or_guest_register_values_in_report(self):
        result=check(build_nine_dot3_program())
        self.assertFalse(result['private_values_emitted'])
        self.assertFalse(result['original_gameplay_coefficients_checked'])
        self.assertNotIn(hex(BASE),str(result))
        self.assertNotIn('instruction_words',result)
        self.assertNotIn('register_contents',result)

    def test_conservative_load_delay_does_not_invent_constant(self):
        # SH immediately following LW sees old r10; the next SH sees load.
        data=list(build_nine_product_program()[:6])
        data.extend([ins(35,16,10,0),ins(41,5,10,0),0,ins(41,5,10,2)])
        report=check(data)
        self.assertEqual(report['straight_line_schedule_candidates']
                         ['single_product_sra12'],1)
        self.assertEqual(report['straight_line_candidate_slot_indices'],[0])


if __name__ == '__main__':
    unittest.main()
