import unittest
from tools.compare_overlays import common_prefix, leading_pointer_run

class OverlayTests(unittest.TestCase):
    def test_common_prefix(self):
        self.assertEqual(common_prefix(b"abcx", b"abcy"), 3)
        self.assertEqual(common_prefix(b"abc", b"abcdef"), 3)
        self.assertEqual(common_prefix(b"", b"x"), 0)

    def test_pointer_run(self):
        words = [0x801a3100, 0x801aa870, 0x801aae50, 0x27bdffa0]
        payload = b"".join(x.to_bytes(4, "little") for x in words)
        self.assertEqual(leading_pointer_run(payload),
                         {"count": 3, "nondecreasing": True})

    def test_pointer_run_rejects_unordered(self):
        payload = (0x80100100).to_bytes(4, "little") + (0x80100000).to_bytes(4, "little")
        self.assertEqual(leading_pointer_run(payload),
                         {"count": 2, "nondecreasing": False})

if __name__ == "__main__":
    unittest.main()
