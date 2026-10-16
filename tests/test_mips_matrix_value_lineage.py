"""Synthetic MIPS Q12-to-matrix data-flow tests, no game asset bytes."""
import struct
import unittest

from tools.audit_gp0_trig_table import TABLE
from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_matrix_value_lineage import summarize
from tools.mips_trig_memory import synthetic_cardinal_table

BASE = 0x80010000
STACK = 0x80120000
MATRIX = STACK + 0x40

def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)

def special(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def run(words, regs=None, max_steps=200):
    image = struct.pack('<%dI' % len(words), *words)
    mem = (MappedMemory().map_region(BASE, image)
           .map_region(TABLE, synthetic_cardinal_table())
           .map_region(STACK, bytes(256), True))
    regs = [0]*32 if regs is None else regs
    regs[5] = MATRIX
    tr = execute(image, BASE, BASE, mem, regs, max_steps=max_steps)
    report = summarize(image, BASE, tr, MATRIX)
    return tr, report, mem


def table_load():
    return [ins(15, 0, 8, 0x800D), ins(35, 8, 9, -0x31BC), 0]


class MatrixValueLineageTests(unittest.TestCase):
    def test_direct_table_lw_to_matrix_sh_after_load_delay(self):
        tr, r, mem = run(table_load()+[ins(41,5,9,0),0])
        self.assertTrue(tr['completed'])
        self.assertEqual(r['observed_packed_q12_load_count'], 1)
        self.assertEqual(r['matrix_slots_written_by_sh'], 1)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'], 1)
        self.assertEqual(r['distinct_q12_load_events_contributing_to_final_matrix'],1)
        self.assertFalse(r['bit_exact_ps1_matrix_math_proven'])
        self.assertFalse(r['private_values_emitted'])
        self.assertNotIn('address',str(r))
        self.assertEqual(mem.read(MATRIX,2),4096)

    def test_immediate_use_after_lw_reads_old_register(self):
        tr,r,_=run([ins(15,0,8,0x800D),ins(35,8,9,-0x41BC),
                    ins(41,5,9,0),ins(41,5,9,2),0])
        self.assertEqual(r['matrix_slots_written_by_sh'],2)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],1)
        self.assertFalse(r['matrix_slots'][0]['has_observed_packed_q12_lineage'])
        self.assertTrue(r['matrix_slots'][1]['has_observed_packed_q12_lineage'])
        self.assertTrue(r['matrix_slots'][0]['has_unresolved_external_contribution'])

    def test_mult_mflo_sra_and_all_nine_halfwords(self):
        words=table_load()+[ins(9,0,10,4096), special(24,rs=9,rt=10),
                            special(18,rd=11),special(3,rt=11,rd=11,sa=12)]
        words += [ins(41,5,11,offset) for offset in range(0,18,2)] + [0]
        tr,r,mem=run(words)
        self.assertTrue(tr['completed'])
        self.assertEqual(r['matrix_slots_written_by_sh'],9)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],9)
        self.assertEqual(r['matrix_slots_with_mult_hilo_lineage'],9)
        self.assertEqual(r['distinct_q12_load_events_contributing_to_final_matrix'],1)
        self.assertTrue(all(x['through_mult_hilo'] for x in r['matrix_slots']))
        self.assertEqual([mem.read(MATRIX+i*2,2) for i in range(9)], [4096]*9)

    def test_store_then_load_stack_spill_preserves_table_lineage(self):
        words=table_load()+[ins(41,29,9,0),ins(33,29,10,0),0,ins(41,5,10,0),0]
        regs=[0]*32;regs[29]=STACK
        _,r,_=run(words,regs)
        self.assertEqual(r['matrix_slots_with_memory_roundtrip_lineage'],1)
        self.assertTrue(r['matrix_slots'][0]['through_memory_roundtrip'])

    def test_store_source_obeys_load_delay(self):
        words=[ins(15,0,8,0x800D),ins(35,8,9,-0x41BC),
               ins(41,29,9,0),0,ins(33,29,10,0),0,ins(41,5,10,0)]
        regs=[0]*32;regs[29]=STACK
        _,r,_=run(words,regs)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],0)

    def test_overwrite_eliminates_observed_table_lineage(self):
        words=table_load()+[ins(41,5,9,0),ins(9,0,10,7),ins(41,5,10,0)]
        _,r,mem=run(words)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],0)
        self.assertEqual(r['distinct_q12_load_events_contributing_to_final_matrix'],0)
        self.assertEqual(mem.read(MATRIX,2),7)

    def test_mult_mflo_without_trig_is_not_trig_lineage(self):
        words=[ins(9,0,8,10),ins(9,0,9,20),special(24,rs=8,rt=9),
               special(18,rd=11),ins(41,5,11,0)]
        _,r,_=run(words)
        self.assertEqual(r['matrix_slots_with_mult_hilo_lineage'],0)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],0)

    def test_failed_load_has_no_false_lineage(self):
        tr,r,_=run([ins(35,8,9,0),ins(41,5,9,0)])
        self.assertFalse(tr['completed'])
        self.assertEqual(r['observed_packed_q12_load_count'],0)
        self.assertEqual(r['matrix_slots_written_by_sh'],0)

    def test_packed_lookup_without_matrix_store(self):
        _,r,_=run(table_load())
        self.assertEqual(r['observed_packed_q12_load_count'],1)
        self.assertEqual(r['distinct_q12_load_events_contributing_to_final_matrix'],0)

    def test_pending_load_at_stop(self):
        _,r,_=run(table_load()[:-1])
        self.assertTrue(r['pending_load_at_stop'])
        self.assertEqual(r['matrix_slots_written_by_sh'],0)

    def test_store_is_not_sh_does_not_count_matrix_slot(self):
        words=table_load()+[ins(43,5,9,0)]
        _,r,_=run(words)
        self.assertEqual(r['matrix_slots_written_by_sh'],0)

    def test_sw_overwrite_invalidates_older_sh_lineage(self):
        words=table_load()+[ins(41,5,9,0),ins(9,0,10,7),ins(43,5,10,0)]
        _,r,_=run(words)
        self.assertEqual(r['matrix_slots_written_by_sh'],0)
        self.assertEqual(r['matrix_slots_with_observed_q12_lineage'],0)

    def test_sb_overwrite_invalidates_affected_halfword_only(self):
        words=table_load()+[ins(41,5,9,0),ins(41,5,9,2),
                            ins(9,0,10,7),ins(40,5,10,1)]
        _,r,_=run(words)
        self.assertEqual(r['matrix_slots_written_by_sh'],1)
        self.assertFalse(r['matrix_slots'][0]['written_by_sh'])
        self.assertTrue(r['matrix_slots'][1]['has_observed_packed_q12_lineage'])

    def test_branch_likely_annulled_store_does_not_change_lineage(self):
        words=table_load()+[ins(20,0,10,1),ins(41,5,9,0),ins(41,5,9,2)]
        regs=[0]*32;regs[10]=1
        tr,r,_=run(words,regs)
        self.assertTrue(tr['completed'])
        self.assertEqual(r['matrix_slots_written_by_sh'],1)
        self.assertFalse(r['matrix_slots'][0]['written_by_sh'])
        self.assertTrue(r['matrix_slots'][1]['has_observed_packed_q12_lineage'])

    def test_multiple_independent_packed_loads_join_at_alu(self):
        words=[ins(15,0,8,0x800D),ins(35,8,9,-0x41BC),0,
               ins(35,8,10,-0x41B8),0,special(33,rs=9,rt=10,rd=11),
               ins(41,5,11,0),0]
        _,r,_=run(words)
        self.assertEqual(r['observed_packed_q12_load_count'],2)
        self.assertEqual(r['matrix_slots'][0]['contributing_lookup_count'],2)
        self.assertEqual(r['distinct_q12_load_events_contributing_to_final_matrix'],2)

    def test_load_event_mismatch_rejected(self):
        tr,r,_=run(table_load())
        image=struct.pack('<%dI'%3,*table_load())
        invalid={**tr, 'load_accesses':()}
        with self.assertRaises(ValueError):
            summarize(image,BASE,invalid,MATRIX)

    def test_extra_store_event_rejected(self):
        tr,r,_=run([0])
        invalid={**tr,'store_addresses':(MATRIX,)}
        with self.assertRaises(ValueError):
            summarize(struct.pack('<I',0),BASE,invalid,MATRIX)

    def test_invalid_matrix_address_rejected(self):
        tr,r,_=run([0])
        with self.assertRaises(ValueError):
            summarize(struct.pack('<I',0),BASE,tr,MATRIX+1)

if __name__=='__main__': unittest.main()
