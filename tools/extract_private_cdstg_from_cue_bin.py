#!/usr/bin/env python3
"""PRIVATE, bounded extraction of CDSTG.BIN from an owner-owned PS1 CUE/BIN.

Supports ONLY a single, raw MODE2/2352 track with INDEX 01 00:00:00,
and ISO9660 directories in Mode2/Form1 (2048 data bytes per sector).
Refuses arbitrary cue paths, unsupported forms and multi-extent files.
The original disc, extracted bytes and per-map images never enter CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile

RAW_SECTOR = 2352
PAYLOAD = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
CDSTG_BYTES = 128 * 0x91000
MAX_ENTRIES = 6000
MAX_DEPTH = 8
MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
CUE_RE = re.compile(
    r'FILE "([^"/\\\r\n]+)" BINARY\n'
    r'  TRACK 01 MODE2/2352\n'
    r'    INDEX 01 00:00:00\n?\Z', re.ASCII)


def read_single_track_cue(cue):
    path = Path(cue)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("invalid owner-private CUE file")
    try:
        content = path.read_bytes().decode("ascii").replace("\r\n", "\n")
    except UnicodeError as exc:
        raise ValueError("CUE is not ASCII") from exc
    match = CUE_RE.fullmatch(content)
    if match is None or match.group(1) in (".", "..") or "\x00" in match.group(1):
        raise ValueError("only one MODE2/2352 track starting at 00:00:00 is supported")
    name = match.group(1)
    if not name.lower().endswith(".bin"):
        raise ValueError("CUE does not reference a BIN filename")
    return path.parent / name


class RawMode2ISO:
    def __init__(self, binary):
        self.path = Path(binary)
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("BIN must be an ordinary owner-private file")
        size = self.path.stat().st_size
        if size < RAW_SECTOR * 20 or size % RAW_SECTOR:
            raise ValueError("BIN size is not a whole number of raw PS1 sectors")
        self.sector_count = size // RAW_SECTOR
        self.file = None

    def __enter__(self):
        self.file = self.path.open("rb")
        return self

    def __exit__(self, *_):
        self.file.close()
        self.file = None

    def user_sector(self, lba):
        if self.file is None:
            raise RuntimeError("ISO reader must be used as a context manager")
        if type(lba) is not int or not 0 <= lba < self.sector_count:
            raise ValueError("ISO extent sector lies outside the BIN")
        self.file.seek(lba * RAW_SECTOR)
        raw = self.file.read(RAW_SECTOR)
        if len(raw) != RAW_SECTOR or raw[:12] != SYNC or raw[15] != 2:
            raise ValueError("invalid Mode2/2352 sector sync/header")
        if raw[16:20] != raw[20:24] or raw[18] & 0x20:
            raise ValueError("Mode2 sector is not a supported XA Form1 block")
        return raw[24:24+PAYLOAD]

    def _extent_bytes(self, start, length):
        if (type(start) is not int or type(length) is not int or
                start < 0 or length <= 0 or
                start + (length + PAYLOAD - 1)//PAYLOAD > self.sector_count):
            raise ValueError("ISO extent outside raw sector range")
        for i in range((length + PAYLOAD - 1)//PAYLOAD):
            yield self.user_sector(start+i)[:min(PAYLOAD,length-i*PAYLOAD)]

    @staticmethod
    def _record(entry):
        if len(entry) < 34 or entry[0] != len(entry):
            raise ValueError("invalid ISO9660 directory record")
        if entry[1] != 0:
            raise ValueError("ISO9660 extended attribute sectors unsupported")
        extent = struct.unpack_from("<I",entry,2)[0]
        size = struct.unpack_from("<I",entry,10)[0]
        if entry[6:10] != struct.pack(">I",extent) or entry[14:18] != struct.pack(">I",size):
            raise ValueError("ISO9660 both-endian extent fields disagree")
        if entry[25] & 0x80:
            raise ValueError("ISO9660 multi-extent file unsupported")
        name_len = entry[32]
        if name_len == 0 or 33+name_len > len(entry):
            raise ValueError("invalid ISO9660 filename length")
        raw_name = entry[33:33+name_len]
        if name_len == 1 and raw_name in (b"\x00",b"\x01"):
            name = ".special"
        else:
            try:
                name = raw_name.decode("ascii").upper()
            except UnicodeError as exc:
                raise ValueError("non-ASCII ISO9660 filename unsupported") from exc
        return {"start":extent,"length":size,
                "directory":bool(entry[25] & 2),"name":name}

    def _directory(self, extent, size):
        if not 1 <= size <= MAX_DIRECTORY_BYTES:
            raise ValueError("ISO9660 directory length out of bounds")
        raw = b"".join(self._extent_bytes(extent,size))
        pos = 0
        while pos < len(raw):
            in_sector = pos % PAYLOAD
            length = raw[pos]
            if length == 0:
                pos += PAYLOAD-in_sector
                continue
            if length < 34 or in_sector+length > PAYLOAD or pos+length > len(raw):
                raise ValueError("malformed ISO9660 directory entry alignment")
            yield self._record(raw[pos:pos+length])
            pos += length

    def find_cdstg(self, *, expected_size=CDSTG_BYTES):
        if type(expected_size) is not int or not 1 <= expected_size <= CDSTG_BYTES:
            raise ValueError("invalid expected private CDSTG byte length")
        pvd = self.user_sector(16)
        if pvd[:7] != b"\x01CD001\x01":
            raise ValueError("ISO9660 primary volume descriptor not found")
        root_len = pvd[156]
        root = self._record(pvd[156:156+root_len])
        if not root["directory"]:
            raise ValueError("ISO9660 root extent is not a directory")
        visited = set()
        queue = [(root["start"],root["length"],0)]
        matches = []
        entries_seen = 0
        while queue:
            extent, length, depth = queue.pop(0)
            key = (extent,length)
            if key in visited:
                continue
            visited.add(key)
            if depth > MAX_DEPTH:
                raise ValueError("ISO9660 directory depth limit exceeded")
            for record in self._directory(extent,length):
                entries_seen += 1
                if entries_seen > MAX_ENTRIES:
                    raise ValueError("ISO9660 directory entry count limit exceeded")
                if record["name"] == ".special":
                    continue
                # Verify extents even before considering a filename.
                if record["length"] == 0:
                    continue
                count = (record["length"]+PAYLOAD-1)//PAYLOAD
                if record["start"] + count > self.sector_count:
                    raise ValueError("ISO9660 directory points past BIN end")
                if record["directory"]:
                    queue.append((record["start"],record["length"],depth+1))
                elif record["name"].split(";")[0] == "CDSTG.BIN":
                    if record["length"] != expected_size:
                        raise ValueError("CDSTG.BIN geometry does not match 128 x 0x91000 bytes")
                    matches.append(record)
        if len(matches) != 1:
            raise ValueError("expected exactly one ISO9660 CDSTG.BIN file")
        return matches[0]

    def extract_private(self, record, directory, *, basename="CDSTG.BIN"):
        directory = Path(directory)
        if (not directory.is_dir() or basename != "CDSTG.BIN" or
                type(record.get("start")) is not int or
                record.get("name","").split(";")[0] != "CDSTG.BIN" or
                type(record.get("length")) is not int):
            raise ValueError("invalid private extraction arguments")
        destination = directory / basename
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("owner-private CDSTG.BIN already exists")
        fd, temp = tempfile.mkstemp(prefix=".private-wa1-cdstg-",dir=directory)
        hasher = hashlib.sha256()
        try:
            with os.fdopen(fd,"wb") as output:
                for chunk in self._extent_bytes(record["start"],record["length"]):
                    output.write(chunk)
                    hasher.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temp,0o600)
            if Path(temp).stat().st_size != record["length"]:
                raise ValueError("incomplete CDSTG extraction")
            os.link(temp,destination)  # NEVER overwrite private originals.
        finally:
            Path(temp).unlink(missing_ok=True)
        return {
            "schema":1,
            "kind":"WA1_PRIVATE_MODE2_FORM1_CDSTG_EXTRACT",
            "filename":basename,
            "source_raw_sector_size":RAW_SECTOR,
            "mode2_form1_user_sector_size":PAYLOAD,
            "source_bin_sector_count":self.sector_count,
            "iso_file_start_lba":record["start"],
            "extracted_bytes":record["length"],
            "cdstg_sha256":hasher.hexdigest(),
            "cue_bin_content_copyrighted_and_not_published":True,
            "only_private_output_created":True,
            "original_disc_revision_not_authenticated_by_geometry":True,
            "gpu_and_scene_reconstruction_not_implied":True,
        }


def extract_from_owner_disc(cue, output_directory, *, expected_size=CDSTG_BYTES):
    binary = read_single_track_cue(cue)
    with RawMode2ISO(binary) as disc:
        located = disc.find_cdstg(expected_size=expected_size)
        return disc.extract_private(located,output_directory)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_cue",type=Path)
    ap.add_argument("private_output_directory",type=Path)
    args=ap.parse_args()
    print(json.dumps(extract_from_owner_disc(args.private_cue,args.private_output_directory),
                     indent=2,sort_keys=True))


if __name__=="__main__":
    main()
