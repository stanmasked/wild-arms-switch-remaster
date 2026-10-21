"""Original-free WAIC v1 packer tests (does not need Pillow)."""
import sys
import unittest
import struct
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pack_private_waic import (  # noqa: E402
    encode_icon, INDEX_BYTES, PALETTE_BYTES, TOTAL_BYTES
)


class PrivateIconPackerTests(unittest.TestCase):
    def setUp(self):
        self.indices = bytes(i & 15 for i in range(INDEX_BYTES))
        self.palette = bytes((i * 5) & 255 for i in range(48))

    def test_binary_header_crc_and_palette_order(self):
        data = encode_icon(self.indices, self.palette)
        self.assertEqual(len(data), TOTAL_BYTES)
        self.assertEqual(data[:4], b"WAIC")
        self.assertEqual(struct.unpack_from("<I", data, 4)[0], 1)
        self.assertEqual(struct.unpack_from("<HHHH", data, 8), (256, 256, 16, 0))
        self.assertEqual(struct.unpack_from("<I", data, 16)[0], PALETTE_BYTES + INDEX_BYTES)
        self.assertEqual(struct.unpack_from("<I", data, 20)[0],
                         zlib.crc32(data[24:]) & 0xFFFFFFFF)
        self.assertEqual(data[24:28], self.palette[:3] + bytes((255,)))
        self.assertEqual(data[24 + 4 * 15 + 3], 255)
        self.assertEqual(data[24 + PALETTE_BYTES:24 + PALETTE_BYTES + 16],
                         bytes(range(16)))

    def test_deterministic_byte_identical_encoding(self):
        self.assertEqual(encode_icon(self.indices, self.palette),
                         encode_icon(self.indices, self.palette))

    def test_rejects_truncated_indices(self):
        with self.assertRaisesRegex(ValueError, "65536"):
            encode_icon(self.indices[:-1], self.palette)

    def test_rejects_8bpp_indices_even_with_16_color_palette(self):
        invalid = bytearray(self.indices)
        invalid[-1] = 16
        with self.assertRaisesRegex(ValueError, "4 bits"):
            encode_icon(invalid, self.palette)

    def test_rejects_wrong_number_of_palette_colors(self):
        with self.assertRaisesRegex(ValueError, "16"):
            encode_icon(self.indices, self.palette[:-1])

    def test_rejects_non_byte_data(self):
        with self.assertRaises(ValueError):
            encode_icon(list(self.indices), self.palette)


if __name__ == "__main__":
    unittest.main()
