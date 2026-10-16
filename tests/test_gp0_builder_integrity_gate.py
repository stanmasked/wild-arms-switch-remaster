"""End-to-end synthetic PS-X EXE with Wild Arms' known code and Q12 addresses.

The fixture is generated entirely from NOPs, hand-assembled MIPS instructions,
and synthetic cardinal Q12 entries. It is NOT an original game executable.
"""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze
from tools.audit_gp0_rotation_matrix_builder import BUILDER, RETURN, CALL
from tools.audit_gp0_trig_table import TABLE, ENTRIES, TABLE_LOAD_PCS
from tools.mips_trig_memory import synthetic_cardinal_table

BASE = 0x80010000


def inst(op, rs=0, rt=0, imm=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&65535)


def special(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn


def fixture(*, drop_lookup=None, overwrite_slot=None, wrong_final_store=False,
            malformed_return=False, branch_skip_lookup=False,
            corrupt_table_addr=False):
    # Enough bytes to cover caller, builder, packed Q12 data and JR delay slot.
    image = bytearray(TABLE - BASE + ENTRIES*4)
    def put(pc, word):
        struct.pack_into('<I',image,pc-BASE,word)
    put(CALL-16, inst(9,29,5,16))
    put(CALL, (3<<26)|((BUILDER>>2)&0x3ffffff))
    put(BUILDER, inst(15,0,8,0x800D))          # LUI t0, 0x800D
    put(BUILDER+4, inst(9,8,8,-0x41BC))       # ADDIU t0,t0,-0x41BC
    if corrupt_table_addr:
        put(BUILDER+4, inst(9,8,8,-0x41B8))
    for pc in TABLE_LOAD_PCS:
        if pc != drop_lookup:
            put(pc,inst(35,8,9,0))           # LW t1,0(t0)
    if branch_skip_lookup:
        # Unconditional J over first known trig LW, with explicit delay NOP.
        pc = TABLE_LOAD_PCS[0]-8
        put(pc,(2<<26)|(((TABLE_LOAD_PCS[0]+4)>>2)&0x3ffffff))
        put(pc+4,0)
    base=0x800B7280
    put(base, inst(9,0,10,4096))              # addiu t2,zero,4096
    put(base+4, special(24,rs=9,rt=10))      # mult t1,t2
    put(base+8, special(18,rd=11))           # mflo t3
    put(base+12,special(3,rt=11,rd=11,sa=12))  # sra t3,t3,12
    for i in range(8):
        put(0x800B72C0+4*i,inst(41,5,11,i*2))
    if overwrite_slot is not None:
        put(0x800B7320,inst(43,5,0,overwrite_slot*2))
    put(RETURN,0 if malformed_return else special(8,rs=31))
    put(RETURN+4,inst(41,5 if not wrong_final_store else 29,11,16))
    table=synthetic_cardinal_table()
    image[TABLE-BASE:TABLE-BASE+len(table)]=table
    header=bytearray(2048)
    header[:8]=b'PS-X EXE'
    struct.pack_into('<II',header,0x18,BASE,len(image))
    return bytes(header)+image


def check(**mutations):
    return analyze(fixture(**mutations),caller_replay=True,max_steps=512)


class BuilderIntegrityGateIntegrationTests(unittest.TestCase):
    def test_exact_known_six_sites_nine_final_sh_and_return_pass(self):
        report=check()
        trace=report['exploratory_trace']
        gate=trace['builder_integrity']
        self.assertTrue(gate['synthetic_end_to_end_evidence_complete'])
        self.assertEqual(gate['requirements_satisfied'],10)
        self.assertEqual(gate['unmet_requirement_codes'],[])
        self.assertEqual(trace['reason'],'stop_pc')
        self.assertEqual(trace['builder_execution_evidence']['known_trig_lw_sites_with_verified_packed_reads'],6)
        self.assertEqual(trace['builder_execution_evidence']['final_matrix_slots_verified_against_static_sh_site'],9)
        self.assertEqual(trace['matrix_value_lineage']['matrix_slots_with_observed_q12_lineage'],9)
        self.assertTrue(trace['builder_execution_evidence']['matrix_slots'][8]['final_sh_from_verified_return_delay_slot'])
        self.assertFalse(gate['original_playstation_matrix_values_compared'])

    def test_missing_one_static_lookup_is_fail_closed(self):
        result=check(drop_lookup=TABLE_LOAD_PCS[-1])
        gate=result['exploratory_trace']['builder_integrity']
        self.assertFalse(gate['synthetic_end_to_end_evidence_complete'])
        self.assertIn('all_known_lookup_sites_present',gate['unmet_requirement_codes'])
        self.assertIn('all_known_lookup_sites_executed_with_packed_lw',gate['unmet_requirement_codes'])

    def test_existing_lw_site_skipped_by_jump_not_assumed_executed(self):
        result=check(branch_skip_lookup=True)
        gate=result['exploratory_trace']['builder_integrity']
        self.assertTrue(gate['checks']['all_known_lookup_sites_present'])
        self.assertFalse(gate['checks']['all_known_lookup_sites_executed_with_packed_lw'])

    def test_later_sw_overwriting_coefficient_revokes_full_path(self):
        result=check(overwrite_slot=0)
        gate=result['exploratory_trace']['builder_integrity']
        self.assertFalse(gate['checks']['all_nine_final_sh_match_builder_sites'])
        self.assertFalse(gate['checks']['all_nine_coefficients_retain_q12_lineage'])

    def test_syntactically_valid_lw_with_wrong_q12_index_still_safe(self):
        result=check(corrupt_table_addr=True)
        gate=result['exploratory_trace']['builder_integrity']
        # Still a packed entry, merely a different artificial index.
        self.assertTrue(gate['synthetic_end_to_end_evidence_complete'])
        self.assertFalse(gate['original_gameplay_inputs_verified'])

    def test_wrong_a1_base_at_return_slot_revokes_ninth_verified_sh(self):
        result=check(wrong_final_store=True)
        gate=result['exploratory_trace']['builder_integrity']
        self.assertFalse(gate['synthetic_end_to_end_evidence_complete'])
        self.assertIn('all_nine_final_sh_match_builder_sites',gate['unmet_requirement_codes'])

    def test_no_jr_return_never_qualifies(self):
        result=check(malformed_return=True)
        gate=result['exploratory_trace']['builder_integrity']
        self.assertFalse(gate['checks']['executed_builder_to_caller_return'])
        self.assertFalse(gate['synthetic_end_to_end_evidence_complete'])

    def test_step_limit_prevents_false_full_path(self):
        result=analyze(fixture(),caller_replay=True,max_steps=30)
        gate=result['exploratory_trace']['builder_integrity']
        self.assertEqual(result['exploratory_trace']['reason'],'step_limit')
        self.assertIn('bounded_guest_completed',gate['unmet_requirement_codes'])
        self.assertFalse(gate['synthetic_end_to_end_evidence_complete'])

    def test_static_only_does_not_invent_guest_integrity(self):
        result=analyze(fixture())
        self.assertIn('builder_opcode_evidence',result)
        self.assertNotIn('exploratory_trace',result)

    def test_explore_from_builder_has_no_caller_transfer_proof(self):
        result=analyze(fixture(),explore=True,max_steps=512,
                       initial_registers={8:TABLE})
        gate=result['exploratory_trace']['builder_integrity']
        self.assertFalse(gate['checks']['executed_caller_to_builder_transfer'])
        self.assertFalse(gate['synthetic_end_to_end_evidence_complete'])

    def test_no_guest_addresses_opcodes_or_numeric_coefficients_emitted(self):
        gate=check()['exploratory_trace']['builder_integrity']
        text=str(gate)
        self.assertFalse(gate['private_values_emitted'])
        self.assertNotIn(hex(TABLE),text)
        self.assertNotIn(hex(BUILDER),text)
        self.assertNotIn('coefficient_values',text)


if __name__=='__main__':unittest.main()
