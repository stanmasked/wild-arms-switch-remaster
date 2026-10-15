import unittest
from tools.find_repeated_regions import matching_regions

class RepeatedRegionTests(unittest.TestCase):
    def test_repeated_three_blocks(self):
        blocks = [b"aa", b"bb", b"cc", b"xx", b"aa", b"bb", b"cc"]
        result = matching_regions(b"".join(blocks), 2, 3)
        self.assertEqual(result, [{"offset_a": 0, "offset_b": 8, "common_bytes": 6, "delta": 8}])

    def test_no_overlap(self):
        result = matching_regions(b"aa" * 8, 2, 2)
        self.assertTrue(all(x["offset_a"] + x["common_bytes"] <= x["offset_b"] for x in result))

    def test_no_match(self):
        self.assertEqual(matching_regions(b"aabbccdd", 2, 2), [])

    def test_reject_bad_block(self):
        with self.assertRaises(ValueError):
            matching_regions(b"abc", 0, 1)

    def test_trailing_partial_ignored(self):
        self.assertEqual(matching_regions(b"aabbx", 2, 1), [])

if __name__ == "__main__":
    unittest.main()
