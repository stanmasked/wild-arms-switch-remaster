import struct
import unittest
from tools.audit_gp0_stack_handoff import (
    addiu_from_sp,move_register,jal_target,scan,analyze_helper)

BASE=0x80010000
SETUP=0x8007790c
RENDER=0x80077d08

def addiu(reg,offset):return (9<<26)|(29<<21)|(reg<<16)|(offset&65535)
def move(dst,src):return (src<<21)|(dst<<11)|33
def jal(target):return (3<<26)|((target>>2)&0x3ffffff)
def pack(*words):return struct.pack(f'<{len(words)}I',*words)

def sequence(offset=32,render_offset=None,move_dest=7):
    if render_offset is None:render_offset=offset
    return pack(addiu(16,offset),move(6,16),jal(SETUP),0,
                addiu(16,render_offset),jal(RENDER),move(move_dest,16),0)

class StackHandoff(unittest.TestCase):
    def test_jal_target(self):
        self.assertEqual(jal_target(jal(SETUP),BASE),SETUP)
        self.assertIsNone(jal_target(0,BASE))
    def test_sp_relative_value(self):
        self.assertEqual(addiu_from_sp(addiu(16,32)),(16,32))
        self.assertEqual(addiu_from_sp(addiu(16,-12)),(16,-12))
    def test_move(self):
        self.assertEqual(move_register(move(6,16)),(6,16))
        self.assertEqual(move_register(move(7,16)),(7,16))
    def test_same_object_handoff(self):
        result=scan(sequence(),BASE)
        self.assertEqual(result['matched_same_stack_offset'],1)
        self.assertEqual(result['handoffs'][0]['a2_source']['stack_offset'],32)
    def test_distinct_object_not_conflated(self):
        self.assertEqual(scan(sequence(32,24),BASE)['matched_same_stack_offset'],0)
    def test_wrong_delay_register_no_render_match(self):
        self.assertIsNone(scan(sequence(move_dest=6),BASE)['handoffs'][0]['render_call'])
    def test_setup_not_present(self):
        self.assertEqual(scan(pack(addiu(16,32),jal(RENDER),move(7,16)),BASE)['handoffs'],[])
    def test_empty_image(self):
        self.assertFalse(scan(b'',BASE)['contents_recovered'])
    def test_helper_register_chain(self):
        words=[0]*49
        words[6]=move(19,6)
        words[45]=move(5,19)
        words[47]=jal(0x800b68e8)
        result=analyze_helper(pack(*words),SETUP)
        self.assertTrue(result['a2_saved_to_s3'])
        self.assertTrue(result['s3_to_a1_before_nested_call'])
        self.assertEqual(result['nested_call'],'0x800B68E8')
    def test_wrong_helper_does_not_claim_chain(self):
        result=analyze_helper(b'\0'*200,SETUP)
        self.assertFalse(result['a2_saved_to_s3'])
        self.assertFalse(result['s3_to_a1_before_nested_call'])

if __name__=='__main__':unittest.main()
