"""Synthetic PS-X EXE matrix-coefficient data lineage integration tests."""
import struct
import unittest

from tools.audit_gp0_matrix_replay_preflight import analyze
from tools.audit_gp0_trig_table import TABLE
from tools.mips_trig_memory import synthetic_cardinal_table

BASE = 0x80010000

def ins(op, rs=0, rt=0, imm=0):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 65535)

def special(fn, rs=0, rt=0, rd=0, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def synthetic_exe(words, table=False):
    image = bytearray(struct.pack('<%dI' % len(words), *words))
    if table:
        offset = TABLE - BASE
        trig = synthetic_cardinal_table()
        image.extend(bytes(offset + len(trig) - len(image)))
        image[offset:offset + len(trig)] = trig
    header = bytearray(2048)
    header[:8] = b'PS-X EXE'
    struct.pack_into('<II', header, 0x18, BASE, len(image))
    return bytes(header) + image


class MatrixValueLineageIntegrationTests(unittest.TestCase):
    def test_all_nine_slots_depend_on_synthetic_packed_q12_via_mult(self):
        words = [ins(15,0,8,0x800D), ins(35,8,9,-0x31BC), 0,
                 ins(9,0,10,4096), special(24,rs=9,rt=10),
                 special(18,rd=11), special(3,rt=11,rd=11,sa=12)]
        words.extend(ins(41,5,11,offset) for offset in range(0,18,2))
        words.append(0)
        report = analyze(synthetic_exe(words, True), start=BASE,
                         end=BASE+4*(len(words)-1), explore=True)
        t = report['exploratory_trace']
        lin = t['matrix_value_lineage']
        self.assertEqual(lin['matrix_slots_written_by_sh'],9)
        self.assertEqual(lin['matrix_slots_with_observed_q12_lineage'],9)
        self.assertEqual(lin['matrix_slots_with_mult_hilo_lineage'],9)
        self.assertEqual(lin['distinct_q12_load_events_contributing_to_final_matrix'],1)
        self.assertEqual(t['memory_read_profile']['read_groups']['packed_trig_lw'],1)
        self.assertFalse(lin['bit_exact_ps1_matrix_math_proven'])
        self.assertFalse(lin['private_values_emitted'])
        self.assertNotIn('matrix_address',str(lin))

    def test_unrelated_table_read_does_not_mark_unrelated_matrix_store(self):
        words = [ins(15,0,8,0x800D), ins(35,8,9,-0x31BC), 0,
                 ins(9,0,10,123), ins(41,5,10,0),0]
        report = analyze(synthetic_exe(words, True),start=BASE,
                         end=BASE+4*(len(words)-1),explore=True)
        lin = report['exploratory_trace']['matrix_value_lineage']
        self.assertEqual(lin['observed_packed_q12_load_count'],1)
        self.assertEqual(lin['matrix_slots_with_observed_q12_lineage'],0)
        self.assertEqual(lin['matrix_slots_written_by_sh'],1)

    def test_failed_load_and_unexecuted_sh_not_counted(self):
        words=[ins(35,8,9,0), ins(41,5,9,0), 0]
        report=analyze(synthetic_exe(words),start=BASE,
                       end=BASE+8,explore=True)
        lin=report['exploratory_trace']['matrix_value_lineage']
        self.assertEqual(lin['observed_packed_q12_load_count'],0)
        self.assertEqual(lin['matrix_slots_written_by_sh'],0)
        self.assertEqual(report['exploratory_trace']['reason'],'ValueError')

    def test_static_only_does_not_make_runtime_lineage_claim(self):
        report=analyze(synthetic_exe([0,0]),start=BASE,end=BASE+4)
        self.assertNotIn('exploratory_trace',report)

if __name__ == '__main__':
    unittest.main()
