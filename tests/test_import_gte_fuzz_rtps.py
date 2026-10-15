import unittest
from tools.import_gte_fuzz_rtps import parse_capture

def capture(op='RTPS', code='01', cut=64):
    inputs=[0]*64
    inputs[32]=4096
    inputs[34]=4096
    inputs[36]=4096
    inputs[0]=((-50 & 0xffff)<<16)|100
    inputs[1]=200
    inputs[58]=100
    outputs=[0]*64
    outputs[19]=200
    outputs[9]=100
    outputs[10]=0xffffffce
    outputs[11]=200
    outputs[14]=0x00d70032
    lines=['Test 1']
    lines += [f'> r[{i}] = 0x{v:08x}' for i,v in enumerate(inputs)]
    lines += [f'GTE 0x{code} {op} (sf=1, lm=0, tx=0, vx=0, mx=0)']
    lines += [f'< r[{i}] = 0x{v:08x}' for i,v in enumerate(outputs[:cut])]
    return '\n'.join(lines)+'\n'

class ConverterContract(unittest.TestCase):
    def test_complete_rtps(self):
        v=parse_capture(capture(),'hardware')[0]
        self.assertEqual(len(v['input']),22)
        self.assertEqual(v['input'][12:15],[100,-50,200])
        self.assertEqual(v['expected']['ir2'],-50)
        self.assertEqual(v['expected']['sz3'],200)

    def test_truncated_rejected(self):
        with self.assertRaises(ValueError): parse_capture(capture(cut=63),'hardware')

    def test_non_rtps_rejected(self):
        with self.assertRaises(ValueError): parse_capture(capture(op='NCLIP',code='06'),'hardware')

    def test_summary_not_a_capture(self):
        with self.assertRaises(ValueError):
            parse_capture('Passed tests: 1150\nFailed tests: 0','hardware')

    def test_duplicate_input_rejected(self):
        with self.assertRaises(ValueError):
            parse_capture(capture().replace('> r[1] =','> r[0] ='),'hardware')

    def test_rejects_self_generated_provenance(self):
        with self.assertRaises(ValueError): parse_capture(capture(),'host_reference')

    def test_external_emulator_label(self):
        v=parse_capture(capture(),'external_emulator')[0]
        self.assertEqual(v['expected']['flag'],0)
        self.assertEqual(v['source'],'external_emulator')

if __name__ == '__main__': unittest.main()
