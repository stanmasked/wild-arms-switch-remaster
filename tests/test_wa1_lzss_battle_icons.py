"""Synthetic original-free coverage of WA1 LZSS, pointer and output limits."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from wa1_lzss import LZSSDecodeError, decode_wa1_lzss  # noqa: E402
from audit_cdflr_verified_lzss import audit_cdflr_lzss  # noqa: E402

STRIDE=0x10000


def compressed_zero_tile():
    # 32768 zero bytes: 1820 references of 18 bytes + final 8 bytes.
    tokens=[bytes((0,0x0f))]*1820+[bytes((0,0x05))]
    encoded=bytearray(struct.pack("<I",0x8000))
    for i in range(0,len(tokens),8):
        encoded.append(0)  # eight dictionary references
        encoded.extend(b"".join(tokens[i:i+8]))
    return bytes(encoded)


def make_slot(*, corrupt_index=None, bad_pointer=False):
    stream=compressed_zero_tile()
    offsets=[]
    at=256
    regions={}
    for i in range(58):
        offsets.append(at)
        if i<42:
            at+=4
        elif i%2==0:
            regions[i]=bytes(512)
            at+=512
        else:
            value=stream if i!=corrupt_index else stream[:100]
            regions[i]=value
            at+=len(value)+(0 if i==57 else 3)
    if at>STRIDE:
        raise AssertionError("synthetic slot exceeds bounded size")
    if corrupt_index == 57:
        # Model an incomplete *final* stream with no following pointer:
        # push its start close enough to the fixed slot boundary that
        # zero-filled trailing space cannot falsely finish decompression.
        offsets[57] = STRIDE - 100
    buf=bytearray(STRIDE)
    for i,o in enumerate(offsets):
        struct.pack_into("<I",buf,i*4,0x80183000+o)
    if bad_pointer:
        struct.pack_into("<I",buf,57*4,0x80183000+offsets[56])
    for i,blob in regions.items():
        buf[offsets[i]:offsets[i]+len(blob)]=blob
    return bytes(buf)


def scan(blob):
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"synthetic-cdflr.bin"
        path.write_bytes(blob)
        return audit_cdflr_lzss(path,slot_bytes=STRIDE)


class WA1LZSSTests(unittest.TestCase):
    def test_literal_only(self):
        data=struct.pack("<I",4)+bytes((0x0f,))+b"abcd"
        self.assertEqual(decode_wa1_lzss(data),(b"abcd",len(data)))

    def test_rolling_dictionary_copy(self):
        data=struct.pack("<I",4)+bytes((1,ord("a"),0xee,0xf0))
        self.assertEqual(decode_wa1_lzss(data),(b"aaaa",len(data)))

    def test_zero_initial_dictionary_large_stream(self):
        data=compressed_zero_tile()
        decoded,used=decode_wa1_lzss(data,max_output=0x8000)
        self.assertEqual(len(decoded),0x8000)
        self.assertEqual(set(decoded),{0})
        self.assertEqual(used,len(data))

    def test_malformed_bounds_or_output_length_fail_closed(self):
        for blob in [b"", b"\x01\x00\x00",struct.pack("<I",0),
                     struct.pack("<I",4)+bytes((0x0f,ord("a")))]:
            with self.subTest(blob=blob), self.assertRaises(LZSSDecodeError):
                decode_wa1_lzss(blob)
        with self.assertRaises(LZSSDecodeError):
            decode_wa1_lzss(struct.pack("<I",0x8001),max_output=0x8000)

    def test_reference_overshoot_fails_closed(self):
        blob=struct.pack("<I",1)+bytes((0,0,15))
        with self.assertRaisesRegex(LZSSDecodeError,"overshoots"):
            decode_wa1_lzss(blob)

    def test_full_synthetic_slot_validates_all_eight_streams(self):
        report=scan(make_slot())
        self.assertEqual(report["candidate_stream_count"],8)
        self.assertEqual(report["decoded_exact_0x8000_stream_count"],8)
        self.assertEqual(report["next_pointer_bounded_valid_count"],7)
        self.assertEqual(report["last_upper_bounded_valid_count"],1)
        self.assertEqual(report["exceptions"],[])
        self.assertTrue(report["interpretation"]["no_original_decompressed_bytes_emitted"])

    def test_last_unbounded_stream_truncation_is_reported(self):
        report=scan(make_slot(corrupt_index=57))
        self.assertEqual(report["candidate_stream_count"],8)
        self.assertEqual(report["decoded_exact_0x8000_stream_count"],7)
        self.assertEqual(report["exceptions"][0]["slot"],0)
        self.assertEqual(report["exceptions"][0]["index"],57)

    def test_corrupt_next_pointer_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"pointer order"):
            scan(make_slot(bad_pointer=True))

    def test_mismatched_record_geometry_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"exact number"):
            scan(make_slot()[:-1])


if __name__=="__main__":
    unittest.main()
