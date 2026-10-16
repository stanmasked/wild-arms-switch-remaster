"""Synthetic integration tests for sanitized successful MIPS memory loads."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze
from tools.audit_gp0_trig_table import TABLE
from tools.mips_trig_memory import synthetic_cardinal_table

BASE = 0x80010000

def ins(op, rs=0, rt=0, val=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(val&0xffff)

def fixture(words, table=False):
    data = bytearray(struct.pack('<%dI'%len(words), *words))
    if table:
        off=TABLE-BASE
        raw=synthetic_cardinal_table()
        data.extend(bytes(off+len(raw)-len(data)))
        data[off:off+len(raw)]=raw
    head=bytearray(2048);head[:8]=b'PS-X EXE'
    struct.pack_into('<II',head,0x18,BASE,len(data))
    return bytes(head)+data

class MatrixLoadProfileTests(unittest.TestCase):
    def test_matrix_preflight_counts_packed_q12_read(self):
        program=[ins(15,0,8,0x800D),ins(35,8,9,-0x41bc),0,0]
        # LUI 0x800D + signed low -0x41BC => 0x800CBE44.
        report=analyze(fixture(program,table=True), start=BASE,end=BASE+12,
                       explore=True)
        loads=report['exploratory_trace']['memory_read_profile']
        self.assertEqual(loads['read_groups']['packed_trig_lw'],1)
        self.assertEqual(loads['distinct_packed_trig_entries'],1)
        self.assertTrue(report['trig_table_mapped_in_image'])
        self.assertFalse(loads['original_rotation_angles_recovered'])
        self.assertNotIn('entry_index',str(loads))

    def test_stack_and_matrix_load_preflight(self):
        # $sp is preinitialized to the synthetic scratch stack.
        words=[ins(35,29,8,0),0,ins(33,5,9,0),0]
        report=analyze(fixture(words),start=BASE,end=BASE+12,explore=True)
        groups=report['exploratory_trace']['memory_read_profile']['read_groups']
        self.assertEqual(groups['scratch_stack_read'],1)
        self.assertEqual(groups['matrix_buffer_read'],1)

    def test_failing_read_not_mistaken_for_zero_angle(self):
        words=[ins(35,8,9,0),0]
        result=analyze(fixture(words),start=BASE,end=BASE+4,explore=True)
        self.assertEqual(result['exploratory_trace']['reason'],'ValueError')
        self.assertEqual(result['exploratory_trace']['memory_read_profile']['successful_load_count'],0)
        self.assertEqual(result['exploratory_trace']['memory_read_profile']['distinct_packed_trig_entries'],0)

    def test_no_exploration_has_no_dynamic_read_summary(self):
        result=analyze(fixture([0,0]),start=BASE,end=BASE+4)
        self.assertNotIn('exploratory_trace',result)

if __name__=='__main__':unittest.main()
