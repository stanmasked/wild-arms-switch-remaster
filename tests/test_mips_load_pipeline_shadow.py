"""Consistent R3000A consecutive-load semantics across shadow analyzers."""
import struct
import unittest

from tools.mips_control_flow import execute
from tools.mips_matrix_memory import MappedMemory
from tools.mips_matrix_value_lineage import summarize as lineage
from tools.mips_trig_index_provenance import summarize as trig_index
from tools.mips_caller_sources import inspect as caller_sources
from tools.mips_call_boundary import available_after_path
from tools.mips_entry_dependencies import read_before_write
from tools.mips_trig_memory import synthetic_cardinal_table
from tools.audit_gp0_trig_table import TABLE

BASE=0x80010000
STACK=0x80120000
MATRIX=STACK+0x40


def op(fn,rs=0,rt=0,imm=0):
    return (fn<<26)|(rs<<21)|(rt<<16)|(imm & 65535)


def r(fn,rs=0,rt=0,rd=0,sa=0):
    return (rs<<21)|(rt<<16)|(rd<<11)|(sa<<6)|fn


class PipelineShadowTests(unittest.TestCase):
    def test_consecutive_loads_keep_first_q12_lineage_until_second_retires(self):
        code=[op(15,0,8,0x800D),op(35,8,9,-0x31BC),
              op(35,29,9,0),op(41,5,9,0),0,op(41,5,9,2),0]
        image=struct.pack('<%dI'%len(code),*code)
        ram=bytearray(128)
        struct.pack_into('<I',ram,0,17)
        memory=(MappedMemory().map_region(BASE,image)
                .map_region(TABLE,synthetic_cardinal_table())
                .map_region(STACK,ram,writable=True))
        gpr=[0]*32;gpr[5]=MATRIX;gpr[29]=STACK
        trace=execute(image,BASE,BASE,memory,gpr)
        self.assertTrue(trace['completed'])
        self.assertEqual(memory.read(MATRIX,2),4096)
        self.assertEqual(memory.read(MATRIX+2,2),17)
        result=lineage(image,BASE,trace,MATRIX)
        self.assertTrue(result['matrix_slots'][0]['has_observed_packed_q12_lineage'])
        self.assertFalse(result['matrix_slots'][1]['has_observed_packed_q12_lineage'])
        self.assertEqual(result['matrix_slots_with_observed_q12_lineage'],1)

    def test_trig_index_shadow_uses_first_load_for_immediate_index_arithmetic(self):
        # LW a0,0(sp) produces 1024; LW a0,4(sp) then SLL a0,2
        # observes 1024, not the old incoming zero or next load's zero.
        code=[op(35,29,4,0),op(35,29,4,4),
              r(0,rt=4,rd=8,sa=2),op(15,0,9,0x800D),
              r(33,rs=9,rt=8,rd=9),op(35,9,10,-0x41BC),0]
        image=struct.pack('<%dI'%len(code),*code)
        ram=bytearray(128)
        struct.pack_into('<I',ram,0,1024)
        memory=(MappedMemory().map_region(BASE,image)
                .map_region(TABLE,synthetic_cardinal_table())
                .map_region(STACK,ram))
        gpr=[0]*32;gpr[29]=STACK
        trace=execute(image,BASE,BASE,memory,gpr)
        self.assertTrue(trace['completed'])
        report=trig_index(image,BASE,trace['visited_pcs'],trace['load_accesses'])
        self.assertEqual(report['packed_table_loads_with_provenance'],1)
        self.assertEqual(report['lookups_with_prior_memory_read_in_address_chain'],1)

    def test_caller_static_shadow_uses_first_of_two_loads_after_second_lw(self):
        before=[op(35,8,4,0),op(35,9,4,0),op(9,4,6,0)]
        words=before+[(3<<26),0]
        image=struct.pack('<%dI'%len(words),*words)
        report=caller_sources(image,BASE,BASE+3*4,lookback_words=3,arguments=(6,))
        self.assertTrue(report['window_usable'])
        self.assertEqual(report['arguments'][0]['incoming_gprs'],[8])
        self.assertEqual(report['arguments'][0]['source_kind'],'memory_derived')

    def test_dynamic_entry_dependencies_respect_first_load_retirement(self):
        words=[op(35,8,4,0),op(35,9,4,0),op(9,4,6,1)]
        image=struct.pack('<%dI'%len(words),*words)
        pcs=[BASE+i*4 for i in range(len(words))]
        self.assertEqual(read_before_write(image,BASE,pcs),(8,9))
        ready,pending=available_after_path(image,BASE,pcs)
        self.assertIn(4,ready)
        self.assertIsNone(pending)

if __name__=='__main__':unittest.main()
