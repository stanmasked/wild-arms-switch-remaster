"""Stage 264G: cross-audit two locally separate full signed-evidence archives.

A reference for independently administered copies, NOT attestation of real
off-host storage. Replication only uses a fully verified exact-byte archive,
creates in a different private directory with O_EXCL and fsync, and never
replaces either copy. Verification rechecks BOTH complete Ed25519 fork
archives in two rounds against separately provided pins, rejects aliases
and changed file or directory identities. No automated fence release.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

try:
    from . import audit_record_witness_publication_equivocation_archive as archive
    from . import audit_record_witness_publication_checkpoint_cas as cas
except ImportError:
    import audit_record_witness_publication_equivocation_archive as archive
    import audit_record_witness_publication_checkpoint_cas as cas

REPORT_SCHEMA='wild-arms-ps1-equivocation-evidence-dual-copy-report-v1'


class DualCopyConflict(archive.EvidenceArchiveConflict):
    """Two signed evidence copies cannot be trusted as consistent."""


def _identity(path):
    """Snapshot the exact private file and its immediate containing directory."""
    path=archive._secure_parent(path)
    try:
        parent=path.parent.lstat()
        item=path.lstat()
    except OSError as exc:
        raise DualCopyConflict('missing or inaccessible archive replica') from exc
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or parent.st_mode & 0o077 or parent.st_nlink < 1
            or not stat.S_ISREG(item.st_mode) or item.st_uid != os.getuid()
            or item.st_mode & 0o077 or item.st_nlink != 1
            or item.st_size < 1 or item.st_size > archive.MAX_ARCHIVE):
        raise DualCopyConflict('unsafe archive replica inode or private directory')
    return ((parent.st_dev,parent.st_ino),
            (item.st_dev,item.st_ino,item.st_size))


def _separate(primary,secondary):
    parent_a,file_a=_identity(primary)
    parent_b,file_b=_identity(secondary)
    if parent_a == parent_b:
        raise DualCopyConflict('archive replicas share their parent directory')
    if file_a[:2] == file_b[:2]:
        raise DualCopyConflict('archive replicas share the same underlying inode')
    return ((parent_a,file_a),(parent_b,file_b))


def _pins(primary_pin,secondary_pin,evidence_pin):
    for p in (primary_pin,secondary_pin,evidence_pin):
        cas.digest(p)
    if not hmac.compare_digest(primary_pin,secondary_pin):
        raise DualCopyConflict('replica exact-byte archive hashes diverge')


def _inspect(path,archive_pin,evidence_pin,public_a,public_b,pem_a,pem_b):
    return archive.inspect(
        path,
        expected_archive_sha256=archive_pin,
        expected_evidence_sha256=evidence_pin,
        operator_a_public=public_a,operator_b_public=public_b,
        external_operator_a_pin=pem_a,external_operator_b_pin=pem_b)


def _read_digest(path,archive_pin):
    raw=archive._read(path)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),archive_pin):
        raise DualCopyConflict('replica differs from independently retained SHA-256')
    return raw


def verify(primary,secondary, *,
           primary_pin,secondary_pin,evidence_pin,
           operator_a_public,operator_b_public,
           external_operator_a_pin,external_operator_b_pin):
    """Observe two exact full archives twice; never write or restore either."""
    _pins(primary_pin,secondary_pin,evidence_pin)
    cas.digest(external_operator_a_pin)
    cas.digest(external_operator_b_pin)
    previous=None
    expected=None
    for _ in range(2):
        identities=_separate(primary,secondary)
        first_raw=_read_digest(primary,primary_pin)
        second_raw=_read_digest(secondary,secondary_pin)
        if not hmac.compare_digest(first_raw,second_raw):
            raise DualCopyConflict('evidence archive byte content diverged')
        report_a=_inspect(primary,primary_pin,evidence_pin,
                          operator_a_public,operator_b_public,
                          external_operator_a_pin,external_operator_b_pin)
        report_b=_inspect(secondary,secondary_pin,evidence_pin,
                          operator_a_public,operator_b_public,
                          external_operator_a_pin,external_operator_b_pin)
        after_a=_read_digest(primary,primary_pin)
        after_b=_read_digest(secondary,secondary_pin)
        if (first_raw != after_a or second_raw != after_b
                or _separate(primary,secondary) != identities):
            raise DualCopyConflict('replica changed during cryptographic audit')
        if (report_a['archive_sha256'] != report_b['archive_sha256']
                or report_a['canonical_evidence_sha256'] !=
                   report_b['canonical_evidence_sha256']):
            raise DualCopyConflict('two signature-verified archive reports disagree')
        current=(identities,hashlib.sha256(first_raw).hexdigest(),
                 report_a['canonical_evidence_sha256'])
        if previous is not None and current != previous:
            raise DualCopyConflict('replicas changed between audit rounds')
        previous=current
        expected=report_a
    return {
        'schema':REPORT_SCHEMA,
        'two_distinct_private_parent_directories_observed':True,
        'two_distinct_regular_file_inodes_observed':True,
        'both_archives_revalidated_twice_with_ed25519':True,
        'both_archive_sha256_pins_matched':True,
        'both_archives_exact_bytes_equal_in_two_rounds':True,
        'no_detected_inode_swap_during_reads':True,
        'canonical_evidence_sha256':expected['canonical_evidence_sha256'],
        'archive_sha256':primary_pin,
        'local_archive_copy_count_observed':2,
        'independent_operator_or_offhost_storage_proved':False,
        'independent_external_pin_retention_proved':False,
        'tamper_or_deletion_prevention_proved':False,
        'physical_durability_proved':False,
        'globally_latest_archive_proved':False,
        'either_branch_keeper_commit_proved':False,
        'automatic_cas_retry_authorized':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def replicate(primary,secondary, *,
              primary_pin,evidence_pin,
              operator_a_public,operator_b_public,
              external_operator_a_pin,external_operator_b_pin):
    """Create second copy exclusively after verifying first, then verify both."""
    cas.digest(primary_pin)
    cas.digest(evidence_pin)
    # Refuse same parent before touching target; file absence is mandatory.
    primary_parent=archive._secure_parent(primary).parent.lstat()
    secondary_parent=archive._secure_parent(secondary).parent.lstat()
    if ((primary_parent.st_dev,primary_parent.st_ino) ==
            (secondary_parent.st_dev,secondary_parent.st_ino)):
        raise DualCopyConflict('replica destination must be in another directory')
    if os.path.lexists(secondary):
        raise DualCopyConflict('replica target already exists, never overwrite')
    before=_identity(primary)
    original=_read_digest(primary,primary_pin)
    _inspect(primary,primary_pin,evidence_pin,operator_a_public,
             operator_b_public,external_operator_a_pin,external_operator_b_pin)
    if _identity(primary) != before or _read_digest(primary,primary_pin) != original:
        raise DualCopyConflict('source archive changed before exclusive replication')
    archive._write_exclusive(secondary,original)
    outcome=verify(primary,secondary,
        primary_pin=primary_pin,secondary_pin=primary_pin,
        evidence_pin=evidence_pin,
        operator_a_public=operator_a_public,
        operator_b_public=operator_b_public,
        external_operator_a_pin=external_operator_a_pin,
        external_operator_b_pin=external_operator_b_pin)
    outcome['local_secondary_no_replace_creation_verified']=True
    return outcome


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('replicate','verify'))
    p.add_argument('primary',type=Path)
    p.add_argument('secondary',type=Path)
    p.add_argument('--primary-pin',required=True)
    p.add_argument('--secondary-pin')
    p.add_argument('--evidence-pin',required=True)
    p.add_argument('--operator-a-public',type=Path,required=True)
    p.add_argument('--operator-b-public',type=Path,required=True)
    p.add_argument('--operator-a-pin',required=True)
    p.add_argument('--operator-b-pin',required=True)
    a=p.parse_args(argv)
    response={'schema':REPORT_SCHEMA,
              'automatic_cas_retry_authorized':False,
              'witness_fence_retirement_authorized':False,
              'witness_fence_retired':False}
    kwargs=dict(primary_pin=a.primary_pin,evidence_pin=a.evidence_pin,
                operator_a_public=a.operator_a_public,
                operator_b_public=a.operator_b_public,
                external_operator_a_pin=a.operator_a_pin,
                external_operator_b_pin=a.operator_b_pin)
    try:
        if a.action=='replicate':
            if a.secondary_pin is not None:
                raise DualCopyConflict('replication cannot claim prior independent secondary pin')
            response.update(replicate(a.primary,a.secondary,**kwargs))
        else:
            if a.secondary_pin is None:
                raise DualCopyConflict('secondary independently retained pin required')
            response.update(verify(a.primary,a.secondary,
                                   secondary_pin=a.secondary_pin,**kwargs))
        status=0
    except (DualCopyConflict,archive.EvidenceArchiveConflict,
            cas.CheckpointCASConflict,ValueError,OSError,TypeError,
            KeyError,IndexError):
        response['replica_integrity_conflict']=True
        status=1
    print(json.dumps(response,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
