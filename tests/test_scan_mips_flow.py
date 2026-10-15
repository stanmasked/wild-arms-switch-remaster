import unittest
from tools.scan_mips_flow import classify, scan

class ControlFlowTests(unittest.TestCase):
    def test_jal_upper_pc_unknown(self):
        item = classify(0x0c01b496, 0x9c)
        self.assertEqual(item['op'], 'jal')
        self.assertEqual(item['target_field'], '0x001b496')
        self.assertNotIn('relative_target', item)

    def test_beq_forward(self):
        self.assertEqual(classify(0x104000a6, 0x64)['relative_target'], 0x300)

    def test_bne_backward(self):
        self.assertEqual(classify(0x1460fffe, 0x50)['relative_target'], 0x4c)

    def test_jr_ra(self):
        self.assertEqual(classify(0x03e00008, 0x20)['register'], 31)

    def test_not_control_flow(self):
        self.assertIsNone(classify(0x27bdffa0, 0x1c))

    def test_scan(self):
        words = [0x27bdffa0, 0x104000a6, 0, 0x03e00008]
        data = b''.join(x.to_bytes(4, 'little') for x in words)
        self.assertEqual([x['offset'] for x in scan(data)], [4, 12])

if __name__ == '__main__':
    unittest.main()
