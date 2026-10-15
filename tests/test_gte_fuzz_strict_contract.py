import unittest
from tools.import_gte_fuzz_rtps import parse_capture
from test_import_gte_fuzz_rtps import capture

class StrictCapture(unittest.TestCase):
    def test_two_rtps_blocks(self):
        self.assertEqual(len(parse_capture(capture()+capture().replace('Test 1','Test 2'),'hardware')),2)

    def test_skip_other_command_between_rtps(self):
        text=capture()+capture(op='NCLIP',code='06')+capture()
        self.assertEqual(len(parse_capture(text,'hardware')),2)

    def test_input_lines_after_command_rejected(self):
        text=capture().replace('GTE 0x01 RTPS (sf=1, lm=0, tx=0, vx=0, mx=0)',
                               'GTE 0x01 RTPS (sf=1, lm=0, tx=0, vx=0, mx=0)\n> r[0] = 0x00000000')
        with self.assertRaises(ValueError):parse_capture(text,'hardware')

    def test_incorrect_opcode_label_rejected(self):
        with self.assertRaises(ValueError):parse_capture(capture(op='NCLIP',code='01'),'hardware')

    def test_invalid_matrix_selection_rejected(self):
        with self.assertRaises(ValueError):
            parse_capture(capture().replace('mx=0','mx=4'),'hardware')

    def test_unexpected_line_inside_block_rejected(self):
        with self.assertRaises(ValueError):
            parse_capture(capture().replace('> r[2] =','UNEXPECTED\n> r[2] ='),'hardware')

    def test_unexpected_line_after_command_rejected(self):
        with self.assertRaises(ValueError):
            parse_capture(capture().replace('< r[1] =','CORRUPTED\n< r[1] ='),'hardware')

    def test_header_between_blocks_allowed(self):
        self.assertEqual(len(parse_capture('==== SINGLE FUZZ ====\n'+capture()+'==== END ====\n','hardware')),1)

if __name__=='__main__':unittest.main()
