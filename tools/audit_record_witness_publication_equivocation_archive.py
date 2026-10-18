"""Stage 264F: reference local, no-overwrite retention of fork evidence.

The complete 12 signed Stage 264E envelopes are archived only after an offline
Ed25519 conflict audit. Retention uses exclusive creation, fsync and a fresh
exact-byte readback. A separately retained archive hash must be provided on
each later verification. This is NOT WORM, independent archival custody,
off-host storage or a production anti-deletion mechanism.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat

try:
    from . import audit_record_witness_publication_highwater_equivocation as eq
    from . import audit_record_witness_publication_checkpoint_cas as cas
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    import audit_record_witness_publication_highwater_equivocation as eq
    import audit_record_witness_publication_checkpoint_cas as cas
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA='wild-arms-ps1-equivocation-evidence-archive-v1'
REPORT_SCHEMA='wild-arms-ps1-equivocation-evidence-archive-report-v1'
MAX_ARCHIVE=65536
META_FIELDS={
    'scope','operator_a_id','operator_b_id','operator_a_pin','operator_b_pin',
    'parent_old_a_pin','parent_old_b_pin',
    'previous_transition_bundle_sha256',
    'expected_parent_generation','expected_parent_pair_pin',
    'expected_parent_event_head',
}
RECORD_FIELDS={'sha256','envelope_b64'}


class EvidenceArchiveConflict(cas.CheckpointCASConflict):
    """Archive, out-of-band pins, custody or signed conflict is unsafe."""


def _create_report(archive_sha, evidence_sha, *, created):
    return {
        'schema':REPORT_SCHEMA,
        'archive_sha256':archive_sha,
        'canonical_evidence_sha256':evidence_sha,
        'archive_no_replace_creation_and_readback_verified':created,
        'archive_exact_independently_pinned_readback_verified':True,
        'archived_sibling_signatures_revalidated':True,
        'external_archive_custody_proved':False,
        'externally_retained_archive_pin_proved':False,
        'tamper_or_deletion_prevention_proved':False,
        'physical_durability_proved':False,
        'either_branch_keeper_commit_proved':False,
        'global_latest_head_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def _expected_meta(meta):
    if type(meta) is not dict or set(meta) != META_FIELDS:
        raise EvidenceArchiveConflict('missing or unexpected archive enrollment metadata')
    if (type(meta['scope']) is not str
            or type(meta['operator_a_id']) is not str
            or type(meta['operator_b_id']) is not str):
        raise EvidenceArchiveConflict('invalid operator archive metadata')
    for key in META_FIELDS - {
            'scope','operator_a_id','operator_b_id','expected_parent_generation'}:
        cas.digest(meta[key])
    cas.number(meta['expected_parent_generation'],cas.MAX_COUNT,
               'parent generation')
    return meta


def _validate_archived(meta, branches, *,
                       operator_a_public, operator_b_public,
                       external_operator_a_pin, external_operator_b_pin,
                       external_evidence_sha256):
    _expected_meta(meta)
    for name,expected in (('operator_a_pin',external_operator_a_pin),
                          ('operator_b_pin',external_operator_b_pin)):
        if not hmac.compare_digest(cas.digest(expected),meta[name]):
            raise EvidenceArchiveConflict('archived enrollment differs from external pins')
    cas.digest(external_evidence_sha256)
    if type(branches) is not dict or set(branches) != {'left','right'}:
        raise EvidenceArchiveConflict('archive does not contain both signed branches')
    unpacked,hashes={},{}
    for direction in ('left','right'):
        records=branches[direction]
        if type(records) is not dict or set(records) != eq.KEYS:
            raise EvidenceArchiveConflict('archive missing complete six-envelope branch')
        unpacked[direction],hashes[direction]={},{}
        for label in eq.KEYS:
            item=records[label]
            if type(item) is not dict or set(item) != RECORD_FIELDS:
                raise EvidenceArchiveConflict('archive envelope metadata malformed')
            pin=cas.digest(item['sha256'])
            encoded=item['envelope_b64']
            if type(encoded) is not str:
                raise EvidenceArchiveConflict('invalid archive envelope encoding')
            try:
                raw=base64.b64decode(encoded,validate=True)
                if base64.b64encode(raw).decode('ascii') != encoded:
                    raise ValueError('noncanonical base64')
            except (ValueError,UnicodeError) as exc:
                raise EvidenceArchiveConflict('invalid canonical base64') from exc
            if (not 0 < len(raw) <= (2048 if label.startswith(('old_','new_'))
                                   else 2048)
                    or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin)):
                raise EvidenceArchiveConflict('archived envelope bytes changed')
            unpacked[direction][label]=raw
            hashes[direction][label]=pin
    result=eq.verify(unpacked['left'],unpacked['right'],
        hashes['left'],hashes['right'],
        scope=meta['scope'],
        operator_a_id=meta['operator_a_id'],
        operator_b_id=meta['operator_b_id'],
        operator_a_public=operator_a_public,
        operator_a_pin=external_operator_a_pin,
        operator_b_public=operator_b_public,
        operator_b_pin=external_operator_b_pin,
        parent_old_a_pin=meta['parent_old_a_pin'],
        parent_old_b_pin=meta['parent_old_b_pin'],
        previous_transition_bundle_sha256=meta['previous_transition_bundle_sha256'],
        expected_parent_generation=meta['expected_parent_generation'],
        expected_parent_pair_pin=meta['expected_parent_pair_pin'],
        expected_parent_event_head=meta['expected_parent_event_head'],
        externally_pinned_evidence_sha256=external_evidence_sha256)
    return result


def _secure_parent(path):
    path=Path(path)
    parent=path.parent
    st=parent.lstat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise EvidenceArchiveConflict('archive parent must be private and owned')
    if path.is_symlink():
        raise EvidenceArchiveConflict('archive symlink forbidden')
    return path


def _write_exclusive(path, raw):
    """Keep uncertain partial writes for manual inspection; NEVER unlink."""
    path=_secure_parent(path)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        parentfd=os.open(path.parent,os.O_RDONLY
                         |getattr(os,'O_DIRECTORY',0))
        try:
            os.fsync(parentfd)
        finally:
            os.close(parentfd)
    except BaseException:
        # If the write/acknowledgment was ambiguous, do not erase the
        # partially written artifact or pretend the file was not created.
        raise


def _read(path):
    """Read the exact private inode once, rejecting links and path swaps."""
    path=_secure_parent(path)
    _private_regular_file(path)
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        current=os.lstat(path)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_mode & 0o077
                or before.st_dev != current.st_dev
                or before.st_ino != current.st_ino or current.st_nlink != 1):
            raise EvidenceArchiveConflict('archive hardlink or inode identity conflict')
        with os.fdopen(fd,'rb',closefd=False) as source:
            raw=source.read(MAX_ARCHIVE+1)
        after=os.fstat(fd)
        current=os.lstat(path)
        if (len(raw)>MAX_ARCHIVE or not raw
                or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or after.st_size != len(raw)
                or current.st_dev != after.st_dev
                or current.st_ino != after.st_ino or current.st_nlink != 1):
            raise EvidenceArchiveConflict('archive changed or exceeded size bound')
        return raw
    finally:
        os.close(fd)


def inspect(path, *, expected_archive_sha256,expected_evidence_sha256,
            operator_a_public, operator_b_public,
            external_operator_a_pin,external_operator_b_pin):
    """Fail closed without independent exact-byte archive/evidence pins."""
    cas.digest(expected_archive_sha256)
    cas.digest(expected_evidence_sha256)
    raw=_read(path)
    archive_hash=hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(archive_hash,expected_archive_sha256):
        raise EvidenceArchiveConflict('archive differs from independently retained pin')
    try:
        parsed=json.loads(raw,object_pairs_hook=cas._unique_json_fields,
                          parse_constant=cas._reject_json_constant)
    except (ValueError,UnicodeError) as exc:
        raise EvidenceArchiveConflict('invalid archive JSON') from exc
    if (type(parsed) is not dict
            or set(parsed) != {'schema','metadata','branches','evidence_sha256'}
            or parsed['schema'] != SCHEMA
            or raw != _canonical(parsed)):
        raise EvidenceArchiveConflict('archive JSON not canonical or correct schema')
    if not hmac.compare_digest(cas.digest(parsed['evidence_sha256']),
                               expected_evidence_sha256):
        raise EvidenceArchiveConflict('archived evidence digest differs')
    _validate_archived(parsed['metadata'],parsed['branches'],
        operator_a_public=operator_a_public,
        operator_b_public=operator_b_public,
        external_operator_a_pin=external_operator_a_pin,
        external_operator_b_pin=external_operator_b_pin,
        external_evidence_sha256=expected_evidence_sha256)
    return _create_report(archive_hash,expected_evidence_sha256,created=False)


def create(path,branch_a,branch_b,pins_a,pins_b, *,
           metadata,expected_evidence_sha256,
           operator_a_public,operator_b_public,
           external_operator_a_pin,external_operator_b_pin):
    """Authentically archive once; no overwrite on replay or failure."""
    meta=_expected_meta(metadata)
    cas.digest(expected_evidence_sha256)
    if (type(branch_a) is not dict or set(branch_a) != eq.KEYS
            or type(branch_b) is not dict or set(branch_b) != eq.KEYS
            or type(pins_a) is not dict or set(pins_a) != eq.KEYS
            or type(pins_b) is not dict or set(pins_b) != eq.KEYS):
        raise EvidenceArchiveConflict('incomplete creation evidence')
    branches={}
    for label,branch,pins in (('left',branch_a,pins_a),
                              ('right',branch_b,pins_b)):
        branches[label]={}
        for item in eq.KEYS:
            raw=branch[item]
            if type(raw) is not bytes:
                raise EvidenceArchiveConflict('signed certificate is not bytes')
            branches[label][item]={
                'sha256':pins[item],
                'envelope_b64':base64.b64encode(raw).decode('ascii')}
    _validate_archived(meta,branches,
        operator_a_public=operator_a_public,
        operator_b_public=operator_b_public,
        external_operator_a_pin=external_operator_a_pin,
        external_operator_b_pin=external_operator_b_pin,
        external_evidence_sha256=expected_evidence_sha256)
    raw=_canonical({'schema':SCHEMA,'metadata':meta,'branches':branches,
                    'evidence_sha256':expected_evidence_sha256})
    if len(raw) > MAX_ARCHIVE:
        raise EvidenceArchiveConflict('archive exceeds strict size bound')
    archive_pin=hashlib.sha256(raw).hexdigest()
    _write_exclusive(path,raw)
    result=inspect(path,expected_archive_sha256=archive_pin,
        expected_evidence_sha256=expected_evidence_sha256,
        operator_a_public=operator_a_public,
        operator_b_public=operator_b_public,
        external_operator_a_pin=external_operator_a_pin,
        external_operator_b_pin=external_operator_b_pin)
    result['archive_no_replace_creation_and_readback_verified']=True
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('create','inspect'))
    p.add_argument('archive',type=Path)
    p.add_argument('--operator-a-public',type=Path,required=True)
    p.add_argument('--operator-b-public',type=Path,required=True)
    p.add_argument('--operator-a-pin',required=True)
    p.add_argument('--operator-b-pin',required=True)
    p.add_argument('--evidence-sha256',required=True)
    p.add_argument('--expected-archive-sha256')
    p.add_argument('--scope')
    p.add_argument('--operator-a-id')
    p.add_argument('--operator-b-id')
    p.add_argument('--parent-old-a-sha256')
    p.add_argument('--parent-old-b-sha256')
    p.add_argument('--previous-transition-bundle-sha256')
    p.add_argument('--expected-parent-generation',type=int)
    p.add_argument('--expected-parent-pair-pin')
    p.add_argument('--expected-parent-event-head')
    for direction in ('left','right'):
        for key in eq.KEYS:
            flag=direction+'-'+key.replace('_','-')
            p.add_argument('--'+flag,type=Path)
            p.add_argument('--'+flag+'-sha256')
    a=p.parse_args(argv)
    report={
        'schema':REPORT_SCHEMA,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
    }
    try:
        if a.action=='inspect':
            if a.expected_archive_sha256 is None:
                raise EvidenceArchiveConflict('missing independent archive pin')
            result=inspect(a.archive,
                expected_archive_sha256=a.expected_archive_sha256,
                expected_evidence_sha256=a.evidence_sha256,
                operator_a_public=a.operator_a_public,
                operator_b_public=a.operator_b_public,
                external_operator_a_pin=a.operator_a_pin,
                external_operator_b_pin=a.operator_b_pin)
        else:
            meta={
                'scope':a.scope,'operator_a_id':a.operator_a_id,
                'operator_b_id':a.operator_b_id,
                'operator_a_pin':a.operator_a_pin,
                'operator_b_pin':a.operator_b_pin,
                'parent_old_a_pin':a.parent_old_a_sha256,
                'parent_old_b_pin':a.parent_old_b_sha256,
                'previous_transition_bundle_sha256':
                    a.previous_transition_bundle_sha256,
                'expected_parent_generation':a.expected_parent_generation,
                'expected_parent_pair_pin':a.expected_parent_pair_pin,
                'expected_parent_event_head':a.expected_parent_event_head,
            }
            signed,pins={},{}
            for direction in ('left','right'):
                signed[direction],pins[direction]={},{}
                for key in eq.KEYS:
                    name=direction+'_'+key
                    if getattr(a,name) is None:
                        raise EvidenceArchiveConflict('missing full signed evidence')
                    signed[direction][key]=_read_limited(
                        _private_regular_file(getattr(a,name)),2048)
                    pins[direction][key]=getattr(a,name+'_sha256')
            result=create(a.archive,signed['left'],signed['right'],
                pins['left'],pins['right'],metadata=meta,
                expected_evidence_sha256=a.evidence_sha256,
                operator_a_public=a.operator_a_public,
                operator_b_public=a.operator_b_public,
                external_operator_a_pin=a.operator_a_pin,
                external_operator_b_pin=a.operator_b_pin)
        report.update(result)
        status=0
    except (EvidenceArchiveConflict,cas.CheckpointCASConflict,
            ValueError,TypeError,KeyError,IndexError,OSError,
            FileExistsError,sqlite3.DatabaseError):
        report['evidence_archive_conflict']=True
        status=1
    print(json.dumps(report,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
