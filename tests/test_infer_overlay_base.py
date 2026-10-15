import unittest
from tools.infer_overlay_base import infer_base, branch_target, jump_low_target

class OverlayBaseTests(unittest.TestCase):
    def test_branch(self):
        self.assertEqual(branch_target(0x104000a6, 0x64), 0x300)

    def test_jump(self):
        self.assertEqual(jump_low_target(0x0805f0c0), 0x17c300)

    def test_consistency(self):
        data = bytearray(0x800)
        for i, offset in enumerate((0x88, 0xfc, 0x160, 0x1e4, 0x1e4, 0x258, 0x2d4)):
            data[4*i:4*i+4] = (0x8017c000 + offset).to_bytes(4, 'little')
        data[0x64:0x68] = (0x104000a6).to_bytes(4, 'little')
        data[0xf4:0xf8] = (0x0805f0c0).to_bytes(4, 'little')
        report = infer_base(data)
        self.assertEqual(report['base_candidate'], '0x8017c000')
        self.assertEqual(report['header_offsets_if_base_correct'],
                         [0x88, 0xfc, 0x160, 0x1e4, 0x1e4, 0x258, 0x2d4])
        self.assertTrue(report['header_pointers_within_prefix'])

    def test_invalid_branch(self):
        with self.assertRaises(ValueError):
            branch_target(0x27bdffa0, 0x64)

    def test_invalid_jump(self):
        with self.assertRaises(ValueError):
            jump_low_target(0x27bdffa0)

if __name__ == '__main__':
    unittest.main()
