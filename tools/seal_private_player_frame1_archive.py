#!/usr/bin/env python3
"""Owner-private Stage516 Frame-1 evidence seal and post-Drive retrieval audit.

This tool does not copy data to GitHub or Google Drive. All SHA-256 values,
source filenames and JSON stay in the private local archive. A matching PNG
is not cryptographic proof of the screenshot's UI origin.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from verify_private_gpudump_player_step1_dump_hash import (
    verify_private_dump_hash_bound_step1_export,
)

ROLES=("native","pretrace","gp0","v2","png")
BASENAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
DIGEST=re.compile(r"[0-9a-f]{64}\Z")
KIND="WA1_PRIVATE_FRAME1_ARCHIVE_SEAL"
MAX_MANIFEST_BYTES=16384


def _name(name):
    if (type(name) is not str or BASENAME.fullmatch(name) is None
            or name in (".","..")):
        raise ValueError("private archive filenames must be plain safe basenames")
    return name


def _paths(root,names):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("private evidence root must be a real directory")
    if type(names) is not dict or set(names)!=set(ROLES):
        raise ValueError("five evidence roles required")
    values=[_name(names[role]) for role in ROLES]
    if len(set(values))!=len(ROLES):
        raise ValueError("evidence roles must have distinct filenames")
    paths=[root/name for name in values]
    identities=[]
    for path in paths:
        st=path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size<1:
            raise ValueError("private evidence must be nonempty regular unlinked files")
        identities.append((st.st_dev,st.st_ino))
    if len(set(identities))!=len(ROLES):
        raise ValueError("different evidence roles alias the same file")
    return paths


def _sha(path):
    digest=hashlib.sha256()
    with open(path,"rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_audit(paths,roi,flags,expected=None):
    if (type(roi) is not dict or set(roi)!=set(("x","y","width","height"))
            or any(type(v) is not int for v in roi.values())):
        raise ValueError("exact integer ROI geometry required")
    if (type(flags) is not dict or set(flags)!={"changed","gp1"}
            or any(type(v) is not bool for v in flags.values())):
        raise ValueError("exact strictness flags required")
    opts=dict(x=roi["x"],y=roi["y"],width=roi["width"],height=roi["height"],
              require_exact_rgb=True,require_changed_roi=flags["changed"],
              require_native_display_window=flags["gp1"])
    if expected is not None:
        opts.update(expected_native_sha256=expected["native"],
                    expected_snapshot_sha256=expected["v2"],
                    expected_png_sha256=expected["png"])
    report=verify_private_dump_hash_bound_step1_export(*paths,**opts)
    if (not report["roi_exact_rgb_equal"] or
            not report["snapshot_native_dump_sha256_matches"] or
            not report["exported_vram_crc32_verified"]):
        raise ValueError("private Frame-1 RGB or native identity not verified")
    return report


def _assert_sealed_file_bytes(paths,files):
    """Check every role independently; native/PNG/V2 checks alone are insufficient."""
    for role,path in zip(ROLES,paths):
        record=files[role]
        if (path.stat().st_size!=record["size"] or
                not hmac.compare_digest(_sha(path),record["sha256"])):
            raise ValueError("archived private evidence differs from manifest")


def seal(root,names,*,roi,require_changed_roi=False,require_gp1=False,
         manifest_name="stage516-frame1.private.json"):
    """Refuse overwrite; private hashes are written only inside owner's root."""
    target=Path(root)/_name(manifest_name)
    if target.exists() or target.is_symlink():
        raise FileExistsError("private seal already exists")
    paths=_paths(root,names)
    flags={"changed":require_changed_roi,"gp1":require_gp1}
    _strict_audit(paths,roi,flags)
    files={}
    for role,path in zip(ROLES,paths):
        files[role]={"name":path.name,"size":path.stat().st_size,
                     "sha256":_sha(path)}
    # Re-audit with independently recomputed expectations before publication.
    _strict_audit(paths,roi,flags,{role:files[role]["sha256"]
                                 for role in ("native","v2","png")})
    # A strict RGB replay binds native/V2/PNG, but the complete manifest
    # also seals GP0 and pretrace files. Re-hash all five before committing.
    _assert_sealed_file_bytes(paths,files)
    record={"kind":KIND,"schema":1,"files":files,"roi":roi,"flags":flags,
            "result":"RGB_EQUALITY_WITH_UNATTESTED_SCREENSHOT_ORIGIN",
            "origin":"operator_claim_not_cryptographically_attested",
            "private_only":True}
    data=(json.dumps(record,indent=2,sort_keys=True)+"\n").encode("utf-8")
    if len(data)>MAX_MANIFEST_BYTES:
        raise ValueError("private seal too large")
    # Write a complete 0600 temporary file, then atomically link it into
    # place without replacing a prior seal. An interrupted write must not
    # leave a truncated manifest occupying its final name.
    temp_name=None
    published=False
    try:
        with tempfile.NamedTemporaryFile(
                dir=Path(root),prefix="."+target.name+".",suffix=".tmp",
                delete=False) as stream:
            temp_name=Path(stream.name)
            os.chmod(temp_name,0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _assert_sealed_file_bytes(paths,files)
        os.link(temp_name,target)
        published=True
        # Detect a concurrent source rewrite during manifest publication.
        _assert_sealed_file_bytes(paths,files)
    except BaseException:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temp_name is not None:
            temp_name.unlink(missing_ok=True)
    return record


def _unique_json(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            raise ValueError("duplicate private manifest key")
        out[k]=v
    return out


def verify(root,manifest_name="stage516-frame1.private.json"):
    """Verify an independently downloaded archive directory byte for byte."""
    root=Path(root)
    path=root/_name(manifest_name)
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=MAX_MANIFEST_BYTES:
        raise ValueError("missing or oversized private manifest")
    record=json.loads(path.read_text("utf-8"),object_pairs_hook=_unique_json)
    if (type(record) is not dict or
            set(record)!={"kind","schema","files","roi","flags","result","origin","private_only"} or
            record["kind"]!=KIND or type(record["schema"]) is not int or record["schema"]!=1 or
            record["private_only"] is not True or
            record["result"]!="RGB_EQUALITY_WITH_UNATTESTED_SCREENSHOT_ORIGIN" or
            record["origin"]!="operator_claim_not_cryptographically_attested"):
        raise ValueError("unknown private manifest schema or provenance")
    entries=record["files"]
    if type(entries) is not dict or set(entries)!=set(ROLES):
        raise ValueError("private manifest roles missing")
    names={}
    for role in ROLES:
        item=entries[role]
        if (type(item) is not dict or set(item)!={"name","size","sha256"} or
                type(item["size"]) is not int or item["size"]<1 or
                type(item["sha256"]) is not str or not DIGEST.fullmatch(item["sha256"])):
            raise ValueError("invalid private evidence entry")
        names[role]=_name(item["name"])
    paths=_paths(root,names)
    _assert_sealed_file_bytes(paths,entries)
    _strict_audit(paths,record["roi"],record["flags"],
                  {role:entries[role]["sha256"] for role in ("native","v2","png")})
    # Guard against accidental changes to GP0 or pretrace while replaying.
    _assert_sealed_file_bytes(paths,entries)
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("seal","verify"))
    p.add_argument("private_directory")
    p.add_argument("--manifest-name",default="stage516-frame1.private.json")
    for role in ROLES:
        p.add_argument("--"+role,required=False)
    for k in ("x","y","width","height"):
        p.add_argument("--"+k,type=int)
    p.add_argument("--require-changed-roi",action="store_true")
    p.add_argument("--require-native-display-window",action="store_true")
    a=p.parse_args()
    if a.action=="seal":
        if any(getattr(a,r) is None for r in ROLES) or any(
                getattr(a,k) is None for k in ("x","y","width","height")):
            p.error("seal requires all five evidence files and exact ROI coordinates")
        seal(a.private_directory,{r:getattr(a,r) for r in ROLES},
             roi={k:getattr(a,k) for k in ("x","y","width","height")},
             require_changed_roi=a.require_changed_roi,
             require_gp1=a.require_native_display_window,
             manifest_name=a.manifest_name)
        print("PRIVATE_FRAME1_SEAL_CREATED; keep manifest and inputs owner-private")
    else:
        verify(a.private_directory,a.manifest_name)
        print("PRIVATE_FRAME1_ARCHIVE_INTEGRITY_AND_RGB_VERIFIED; PNG origin unverified")


if __name__=="__main__":
    main()
