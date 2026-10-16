"""Check opcode reconnaissance integrated with synthetic PS-X EXE preflight."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze
from tools.audit_gp0_rotation_matrix_builder import BUILDER, RETURN
from tools.audit_gp0_trig_table import TABLE_LOAD_PCS
from tools.mips_q12_differential import build_nine_product_program

BASE=0x80010000


def ins(op,rs=0,rt=0,imm=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&65535)


def exe(words,base=BASE):
    image=struct.pack('<%dI'%len(words),*words)
    head=bytearray(2048);head[:8]=b'PS-X EXE'
    struct.pack_into('<II',head,0x18,base,len(image))
    return bytes(head)+image


class BuilderOpcodeEvidenceIntegrationTests(unittest.TestCase):
    def test_static_evidence_for_synthetic_nine_products(self):
        code=build_nine_product_program()
        report=analyze(exe(code),start=BASE,end=BASE+len(code)*4-4)
        evid=report['builder_opcode_evidence']
        self.assertEqual(evid['straight_line_schedule_candidates']
                         ['single_product_sra12'],9)
        self.assertTrue(evid['all_nine_slots_statically_referenced'])
        self.assertFalse(evid['static_words_are_executed'])
        self.assertNotIn('exploratory_trace',report)

    def test_exploratory_and_static_are_separate_evidence(self):
        code=build_nine_product_program()+(0,)
        report=analyze(exe(code),start=BASE,end=BASE+len(code)*4-4,
                       explore=True,max_steps=500,
                       initial_registers={16:0x80120000,17:0x80120020})
        self.assertEqual(report['builder_opcode_evidence']
                         ['straight_line_schedule_candidates']['single_product_sra12'],9)
        self.assertEqual(report['exploratory_trace']['matrix_operation_schedule']
                         ['arithmetic_schedule_counts']['single_product_sra12'],9)
        self.assertFalse(report['builder_opcode_evidence']['original_builder_schedule_identified'])

    def test_default_builder_range_actual_addresses_synthetic_bytes(self):
        n=(RETURN-BUILDER)//4+2
        words=[0]*n
        for pc in TABLE_LOAD_PCS:
            words[(pc-BUILDER)//4]=ins(35,8,9,0)
        for slot in range(8):
            words[110+slot]=ins(41,5,10,slot*2)
        words[(RETURN-BUILDER)//4]=(31<<21)|8
        words[(RETURN-BUILDER)//4+1]=ins(41,5,10,16)
        report=analyze(exe(words,BUILDER))
        e=report['builder_opcode_evidence']
        self.assertTrue(report['valid_range'])
        self.assertEqual(e['known_lookup_sites_with_lw_opcode'],6)
        self.assertTrue(e['return_site_encodes_jr_ra'])
        self.assertEqual(e['return_delay_slot_matrix_sh_slot_index'],8)
        self.assertTrue(e['all_nine_slots_referenced_including_return_delay_slot'])
        self.assertFalse(e['original_builder_schedule_identified'])

    def test_missing_builder_range_is_explicit_not_fabricated(self):
        report=analyze(exe([0,0]))
        self.assertFalse(report['valid_range'])
        self.assertNotIn('builder_opcode_evidence',report)

    def test_static_evidence_has_no_game_bytes_or_coefficients(self):
        code=build_nine_product_program()
        report=analyze(exe(code),start=BASE,end=BASE+len(code)*4-4)
        e=report['builder_opcode_evidence']
        self.assertFalse(e['private_values_emitted'])
        self.assertFalse(e['original_gameplay_coefficients_checked'])
        self.assertNotIn('0x8001',str(e))
        self.assertNotIn('coefficient_values',e)

    def test_out_of_image_range_skips_opcode_audit(self):
        r=analyze(exe([0,0]),start=BASE,end=BASE+8)
        self.assertFalse(r['valid_range'])
        self.assertNotIn('builder_opcode_evidence',r)


if __name__=='__main__':unittest.main()
