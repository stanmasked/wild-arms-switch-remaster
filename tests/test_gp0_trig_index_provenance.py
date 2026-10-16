"""Synthetic PS-X EXE integration tests of privacy-safe Q12 index provenance."""
import struct
import unittest
from tools.audit_gp0_matrix_replay_preflight import analyze
from tools.audit_gp0_trig_table import TABLE
from tools.mips_trig_memory import synthetic_cardinal_table

BASE=0x80010000

def i(op,rs=0,rt=0,imm=0):
    return (op<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)

def r(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn

def exe(words, table=False):
    image=bytearray(struct.pack('<%dI'%len(words), *words))
    if table:
        offset=TABLE-BASE
        raw=synthetic_cardinal_table()
        image.extend(bytes(offset+len(raw)-len(image)))
        image[offset:offset+len(raw)]=raw
    head=bytearray(2048); head[:8]=b'PS-X EXE'
    struct.pack_into('<II',head,0x18,BASE,len(image))
    return bytes(head)+image

class SyntheticTrigProvenanceIntegration(unittest.TestCase):
    def test_a0_mask_shift_and_table_index_in_private_preflight(self):
        words=[i(12,4,8,0x0fff),r(0,rt=8,rd=8,sa=2),i(15,0,9,0x800d),
               r(33,rs=9,rt=8,rd=9),i(35,9,10,-0x41bc),0,0]
        summary=analyze(exe(words,table=True),start=BASE,end=BASE+24,
                        explore=True, initial_registers={4:1024})
        profile=summary['exploratory_trace']['trig_address_provenance']
        self.assertTrue(summary['trig_table_mapped_in_image'])
        self.assertEqual(profile['packed_table_loads_with_provenance'],1)
        self.assertEqual(profile['address_dependency_gprs'],[4])
        self.assertEqual(profile['lookups_with_shift_left_two_in_address_chain'],1)
        self.assertEqual(profile['lookups_with_12bit_mask_in_address_chain'],1)
        self.assertFalse(profile['original_angle_values_recovered'])
        self.assertNotIn('coefficient',str(profile))

    def test_failed_unmapped_load_contributes_no_index_evidence(self):
        words=[i(35,8,9,0),0]
        summary=analyze(exe(words),start=BASE,end=BASE+4,explore=True)
        self.assertEqual(summary['exploratory_trace']['reason'],'ValueError')
        self.assertEqual(summary['exploratory_trace']['trig_address_provenance']['packed_table_loads_with_provenance'],0)

    def test_static_only_mode_has_no_dynamic_provenance(self):
        summary=analyze(exe([0,0]),start=BASE,end=BASE+4)
        self.assertNotIn('exploratory_trace',summary)

    def test_supplied_a0_not_proven_to_be_real_rotation_angle(self):
        words=[i(12,4,8,0x0fff),r(0,rt=8,rd=8,sa=2),i(15,0,9,0x800d),
               r(33,rs=9,rt=8,rd=9),i(35,9,10,-0x41bc),0,0]
        report=analyze(exe(words,table=True),start=BASE,end=BASE+24,
                       explore=True,initial_registers={4:0})
        provenance=report['exploratory_trace']['trig_address_provenance']
        self.assertFalse(provenance['input_gpr_proven_to_be_game_angle'])
        self.assertFalse(provenance['private_values_emitted'])

if __name__=='__main__': unittest.main()
