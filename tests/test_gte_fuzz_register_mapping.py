"""Independent register layout contract based on psx-spx GTE register map."""
import unittest
from tools.import_gte_fuzz_rtps import parse_capture

def pack(low, high=0):
    return (low & 0xffff) | ((high & 0xffff) << 16)

def vector_capture():
    before, after = [0]*64, [0]*64
    coeff = [-32768,-123,3,4,5,6,7,8,32767]
    before[32:37] = [pack(coeff[0],coeff[1]),pack(coeff[2],coeff[3]),
                     pack(coeff[4],coeff[5]),pack(coeff[6],coeff[7]),pack(coeff[8])]
    before[37:40] = [0x80000000,123456789,0x7fffffff]
    before[0], before[1] = pack(-1,32767), pack(-32768)
    before[58] = 65535
    before[56], before[57] = 0x80000000,0x7fffffff
    before[59], before[60] = pack(-17),0xffff0001
    after[14], after[19] = 0x80007fff,0xffff
    after[8:12] = [4096,pack(-32768),pack(32767),pack(-1)]
    after[24:28] = [0x80000000,0xffffffff,0x7fffffff,0xfffffffe]
    after[63] = 0x80060000
    lines = ['Test 37']
    lines.extend(f'> r[{i}] = 0x{value:08x}' for i,value in enumerate(before))
    lines.append('GTE 0x01 RTPS (sf=1, lm=0, tx=0, vx=0, mx=0)')
    lines.extend(f'< r[{i}] = 0x{value:08x}' for i,value in enumerate(after))
    return '\n'.join(lines)+'\n', coeff

class RegisterMapping(unittest.TestCase):
    def test_every_input_field_and_output_register(self):
        capture, coeff = vector_capture()
        vector = parse_capture(capture,'external_emulator')[0]
        self.assertEqual(vector['name'],'Test 37')
        self.assertEqual(vector['input'],coeff+[
            -2147483648,123456789,2147483647,
            -1,32767,-32768,65535,
            -2147483648,2147483647,-17,-65535,1,0])
        self.assertEqual(vector['expected'],{
            'sxy2':0x80007fff,'sz3':65535,'ir0':4096,
            'ir1':-32768,'ir2':32767,'ir3':-1,
            'mac0':-2147483648,'mac1':-1,
            'mac2':2147483647,'mac3':-2,'flag':0x80060000})

    def test_sf_lm_mapping(self):
        capture,_=vector_capture()
        capture=capture.replace('sf=1, lm=0','sf=0, lm=1')
        vector=parse_capture(capture,'hardware')[0]
        self.assertEqual(vector['input'][-2:],[0,1])

    def test_signed_mac_and_vertex_boundaries(self):
        capture,_=vector_capture()
        vector=parse_capture(capture,'hardware')[0]
        self.assertEqual(vector['expected']['mac0'],-2147483648)
        self.assertEqual(vector['input'][14],-32768)
        self.assertEqual(vector['input'][0],-32768)

if __name__=='__main__':
    unittest.main()
