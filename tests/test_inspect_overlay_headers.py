import io
import unittest
from tools.inspect_overlay_headers import analyze_header, read_prefix, SYNC

class OverlayHeaderTests(unittest.TestCase):
    def test_mips_prologue_candidate(self):
        words = [0x8017c088, 0x8017c0fc, 0x27bdffa0, 0xafb20050, 0xafbf0058]
        result = analyze_header(b''.join(w.to_bytes(4, 'little') for w in words))
        self.assertEqual(result['initial_address_words'], 2)
        self.assertEqual([x['offset'] for x in result['mips_instruction_candidates']], [8, 12, 16])

    def test_unsorted_address_run(self):
        b = (0x80101000).to_bytes(4, 'little') + (0x80100000).to_bytes(4, 'little')
        self.assertFalse(analyze_header(b)['initial_addresses_nondecreasing'])

    def test_sector_guardrails(self):
        sector = bytearray(2352)
        sector[:12] = SYNC
        sector[15] = 2
        sector[16:20] = sector[20:24] = bytes([0, 8, 0, 0])
        sector[24:28] = b'ABCD'
        e = {'lba': 0, 'size': 4}
        self.assertEqual(read_prefix(io.BytesIO(sector), e), b'ABCD')
        sector[18] |= 0x20
        with self.assertRaises(ValueError):
            read_prefix(io.BytesIO(sector), e)

if __name__ == '__main__':
    unittest.main()
