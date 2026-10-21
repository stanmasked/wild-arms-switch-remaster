"""No-Wild-Arms-asset tests of the bounded private raw PS1 ISO extractor."""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from extract_private_cdstg_from_cue_bin import (  # noqa: E402
    CDSTG_BYTES, PAYLOAD, RAW_SECTOR, SYNC, RawMode2ISO,
    extract_from_owner_disc, read_single_track_cue,
)

BYTES = b"SYNTHETIC-TEST-CDSTG-123"  # Not original game data.
SECTORS = 24


def record(name,start,length,*,folder=False,flags=0):
    if name is None:
        raw_name=b"\x00"
    elif name=="..":
        raw_name=b"\x01"
    else:
        raw_name=name.encode("ascii")
    size = 33 + len(raw_name) + (len(raw_name)%2==0)
    entry=bytearray(size)
    entry[0]=size
    struct.pack_into("<I",entry,2,start)
    struct.pack_into(">I",entry,6,start)
    struct.pack_into("<I",entry,10,length)
    struct.pack_into(">I",entry,14,length)
    entry[25]=flags | (2 if folder else 0)
    entry[28:32]=b"\x01\x00\x00\x01"
    entry[32]=len(raw_name)
    entry[33:33+len(raw_name)]=raw_name
    return bytes(entry)


def raw_mode2(payload,*,form2=False,corrupt_copy=False):
    sector=bytearray(RAW_SECTOR)
    sector[:12]=SYNC
    sector[15]=2
    if form2:
        sector[18]=0x20
        sector[22]=0x20
    if corrupt_copy:
        sector[20]=9
    sector[24:24+len(payload)]=payload
    return bytes(sector)


def synthetic_disc(path, *, file_data=BYTES, form2_lba=None,
                   root_endian_bad=False, wrong_pvd=False,
                   file_flags=0, file_lba=18, file_length=None):
    pvd=bytearray(PAYLOAD)
    pvd[:7]=b"\x01CD001\x01" if not wrong_pvd else b"\x01BAD001\x01"
    root=bytearray(record(None,17,PAYLOAD,folder=True))
    if root_endian_bad:
        root[6]=19
    pvd[156:156+len(root)]=root
    directory=bytearray(PAYLOAD)
    entries=[
        record(None,17,PAYLOAD,folder=True),
        record("..",17,PAYLOAD,folder=True),
        record("CDSTG.BIN;1",file_lba,
               len(file_data) if file_length is None else file_length,
               flags=file_flags),
    ]
    offset=0
    for entry in entries:
        directory[offset:offset+len(entry)]=entry
        offset+=len(entry)
    sectors=[raw_mode2(bytes(PAYLOAD)) for _ in range(SECTORS)]
    sectors[16]=raw_mode2(pvd)
    sectors[17]=raw_mode2(directory)
    if 0 <= file_lba < SECTORS:
        sectors[file_lba]=raw_mode2(file_data,form2=form2_lba==file_lba)
    path.write_bytes(b"".join(sectors))


def cue(path, filename="synthetic.bin"):
    path.write_text(f'FILE "{filename}" BINARY\r\n'
                    '  TRACK 01 MODE2/2352\r\n'
                    '    INDEX 01 00:00:00\r\n',encoding="ascii")


class Stage435DiscExtractionTests(unittest.TestCase):
    def fixtures(self, directory, **opts):
        root=Path(directory)
        binary=root/"synthetic.bin"
        synthetic_disc(binary,**opts)
        descriptor=root/"synthetic.cue"
        cue(descriptor)
        output=root/"extracted"
        output.mkdir()
        return descriptor,binary,output

    def test_real_one_track_cue_syntax_and_sibling_bin(self):
        with tempfile.TemporaryDirectory() as td:
            c,b,_=self.fixtures(td)
            self.assertEqual(read_single_track_cue(c),b)

    def test_extract_complete_raw_mode2_form1_iso_cd_resource(self):
        with tempfile.TemporaryDirectory() as td:
            c,b,out=self.fixtures(td)
            result=extract_from_owner_disc(c,out,expected_size=len(BYTES))
            extracted=out/"CDSTG.BIN"
            self.assertEqual(extracted.read_bytes(),BYTES)
            self.assertEqual(result["extracted_bytes"],len(BYTES))
            self.assertEqual(result["iso_file_start_lba"],18)
            self.assertEqual(result["source_bin_sector_count"],SECTORS)
            self.assertEqual(result["cdstg_sha256"],
                             hashlib.sha256(BYTES).hexdigest())
            self.assertTrue(result["only_private_output_created"])
            self.assertNotIn("original_rgb",json.dumps(result))
            if os.name != "nt":
                self.assertEqual(extracted.stat().st_mode & 0o777,0o600)

    def test_wrong_length_refused_before_file_output(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            with self.assertRaisesRegex(ValueError,"geometry"):
                extract_from_owner_disc(c,out)
            self.assertEqual(list(out.iterdir()),[])

    def test_destination_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            destination=out/"CDSTG.BIN"
            destination.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))
            self.assertEqual(destination.read_bytes(),b"KEEP")

    def test_reject_unsupported_multi_track_cue(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            with c.open("a") as f:
                f.write("  TRACK 02 AUDIO\n")
            with self.assertRaisesRegex(ValueError,"one MODE2"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))

    def test_reject_unsafe_cue_bin_paths(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            for name in ("../escape.bin","sub/file.bin","\\server.bin",".."):
                with self.subTest(name=name):
                    cue(c,name)
                    with self.assertRaises(ValueError):
                        extract_from_owner_disc(c,out,expected_size=len(BYTES))

    def test_reject_raw_bin_size_not_multiple_2352(self):
        with tempfile.TemporaryDirectory() as td:
            c,b,out=self.fixtures(td)
            with b.open("ab") as f:
                f.write(b"Z")
            with self.assertRaisesRegex(ValueError,"raw PS1 sectors"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))

    def test_reject_missing_pvd_or_invalid_both_endian_root(self):
        for modification in ({"wrong_pvd":True},
                             {"root_endian_bad":True}):
            with self.subTest(modification=modification),tempfile.TemporaryDirectory() as td:
                c,_,out=self.fixtures(td,**modification)
                with self.assertRaises(ValueError):
                    extract_from_owner_disc(c,out,expected_size=len(BYTES))
                self.assertEqual(list(out.iterdir()),[])

    def test_reject_wrong_iso_extent_size(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td,file_length=SECTORS*PAYLOAD)
            with self.assertRaisesRegex(ValueError,"past BIN end"):
                extract_from_owner_disc(c,out,expected_size=SECTORS*PAYLOAD)
            self.assertEqual(list(out.iterdir()),[])

    def test_reject_form2_in_target_file(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td,form2_lba=18)
            with self.assertRaisesRegex(ValueError,"Form1"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))
            self.assertEqual(list(out.iterdir()),[])

    def test_reject_multiextent_file(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td,file_flags=0x80)
            with self.assertRaisesRegex(ValueError,"multi-extent"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))
            self.assertEqual(list(out.iterdir()),[])

    def test_reject_sector_corrupted_subheader_copy(self):
        with tempfile.TemporaryDirectory() as td:
            c,b,out=self.fixtures(td)
            with b.open("r+b") as f:
                f.seek(18*RAW_SECTOR+20)
                f.write(b"Z")
            with self.assertRaisesRegex(ValueError,"Form1"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))

    def test_reader_rejects_out_of_bounds_lba(self):
        with tempfile.TemporaryDirectory() as td:
            _,b,_=self.fixtures(td)
            with RawMode2ISO(b) as iso:
                with self.assertRaisesRegex(ValueError,"outside"):
                    iso.user_sector(SECTORS)
                with self.assertRaisesRegex(ValueError,"outside"):
                    iso.user_sector(-1)

    def test_reject_missing_private_directory(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            with self.assertRaisesRegex(ValueError,"invalid private"):
                extract_from_owner_disc(c,out/"missing",expected_size=len(BYTES))

    def test_bad_sync_rejected_before_data_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            c,b,out=self.fixtures(td)
            with b.open("r+b") as f:
                f.seek(16*RAW_SECTOR)
                f.write(b"bad")
            with self.assertRaisesRegex(ValueError,"sync"):
                extract_from_owner_disc(c,out,expected_size=len(BYTES))

    def test_metadata_never_contains_raw_disc_or_resource_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            c,_,out=self.fixtures(td)
            result=extract_from_owner_disc(c,out,expected_size=len(BYTES))
            encoded=json.dumps(result)
            self.assertNotIn(BYTES.decode(),encoded)
            self.assertNotIn("disc_raw_sector_bytes",encoded)
            self.assertTrue(result["original_disc_revision_not_authenticated_by_geometry"])


if __name__=="__main__":
    unittest.main()
