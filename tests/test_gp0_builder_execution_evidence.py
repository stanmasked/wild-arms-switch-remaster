"""Synthetic PS-X EXE integration of static-vs-executed builder evidence."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze, STACK_BASE
from tools.mips_q12_differential import build_nine_product_program,build_nine_dot3_program
from tools.mips_trig_memory import synthetic_cardinal_table
from tools.audit_gp0_trig_table import TABLE

BASE=0x80010000

def ins(op,rs=0,rt=0,imm=0):
    return op<<26 | rs<<21 | rt<<16 | (imm & 65535)

def exe(words,table=False):
    image=bytearray(struct.pack('<%dI'%len(words),*words))
    if table:
        offset=TABLE-BASE
        raw=synthetic_cardinal_table()
        image.extend(bytes(offset+len(raw)-len(image)))
        image[offset:offset+len(raw)]=raw
    head=bytearray(2048)
    head[:8]=b'PS-X EXE'
    struct.pack_into('<II',head,0x18,BASE,len(image))
    return bytes(head)+image

class BuilderExecutionEvidenceIntegrationTests(unittest.TestCase):
    def test_full_synthetic_nine_sh_builder_attestation(self):
        code=build_nine_product_program()
        report=analyze(exe(code+(0,)),start=BASE,end=BASE+len(code)*4,
                       explore=True,max_steps=len(code)+5,
                       initial_registers={16:STACK_BASE+0x100,17:STACK_BASE+0x200})
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertEqual(evidence['final_matrix_slots_verified_against_static_sh_site'],9)
        self.assertEqual(evidence['final_verified_slots_with_recognized_arithmetic_schedule'],9)
        self.assertEqual(evidence['static_matrix_sh_syntax_sites_not_executed'],0)
        self.assertTrue(evidence['guest_execution_completed'])
        self.assertFalse(evidence['original_builder_reachability_proven'])
        self.assertFalse(evidence['private_values_emitted'])

    def test_dot3_shift_each_observed_not_just_present(self):
        code=build_nine_dot3_program(shift_each=True)
        report=analyze(exe(code+(0,)),start=BASE,end=BASE+len(code)*4,
                       explore=True,max_steps=len(code)+5,
                       initial_registers={16:STACK_BASE+0x100,17:STACK_BASE+0x200})
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertEqual(evidence['final_verified_slots_with_recognized_arithmetic_schedule'],9)
        self.assertTrue(all(s['observed_arithmetic_schedule']=='shift_each_of_three_products'
                            for s in evidence['matrix_slots']))

    def test_skipped_branch_static_sh_site_not_execution_evidence(self):
        jump=(2<<26)|(((BASE+20)>>2)&0x3ffffff)
        words=(jump,0,ins(41,5,9,0),0,0,ins(41,5,9,2),0)
        report=analyze(exe(words),start=BASE,end=BASE+24,explore=True,max_steps=25)
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertEqual(evidence['static_matrix_sh_syntax_site_count'],2)
        self.assertEqual(evidence['static_matrix_sh_syntax_sites_not_executed'],1)
        self.assertEqual(evidence['final_matrix_slots_verified_against_static_sh_site'],1)

    def test_unmapped_failed_load_produces_no_fake_static_site_execution(self):
        words=(ins(35,8,9,0),ins(41,5,9,0),0)
        report=analyze(exe(words),start=BASE,end=BASE+8,explore=True)
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertEqual(evidence['final_matrix_slots_verified_against_static_sh_site'],0)
        self.assertEqual(evidence['static_matrix_sh_syntax_sites_not_executed'],1)
        self.assertFalse(evidence['guest_execution_completed'])

    def test_dynamic_confirmed_packed_table_read_not_gameplay_proof(self):
        words=(ins(15,0,8,0x800D),ins(35,8,9,-0x31bc),0,0)
        report=analyze(exe(words,True),start=BASE,end=BASE+12,
                       explore=True,max_steps=20)
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertEqual(evidence['successful_packed_table_load_events_in_trace'],1)
        self.assertEqual(evidence['known_trig_lw_sites_executed'],0)
        self.assertFalse(evidence['original_gameplay_coefficients_checked'])

    def test_static_only_does_not_report_guest_execution_evidence(self):
        report=analyze(exe((0,0)),start=BASE,end=BASE+4)
        self.assertIn('builder_opcode_evidence',report)
        self.assertNotIn('exploratory_trace',report)

    def test_report_omits_private_address_and_coefficient_values(self):
        code=build_nine_product_program()
        report=analyze(exe(code+(0,)),start=BASE,end=BASE+len(code)*4,
                       explore=True,max_steps=len(code)+5,
                       initial_registers={16:STACK_BASE+0x100,17:STACK_BASE+0x200})
        evidence=report['exploratory_trace']['builder_execution_evidence']
        self.assertNotIn('0x801',str(evidence))
        self.assertNotIn('coefficient_values',str(evidence))
        self.assertFalse(evidence['private_values_emitted'])

if __name__=='__main__':unittest.main()
