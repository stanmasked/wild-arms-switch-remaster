"""Stage 263U: independently pinned comparison of two signed mirror histories.

Verify each complete Stage 263T archive, with ITS OWN externally retained
file SHA-256 and latest two-admin signed epoch pin, against the same
read-only publication mirror pair; then require exact identical signed
envelopes for EVERY epoch.

This detects conflicting but validly signed submitted histories, not
unsubmitted forks, synchronized rollback or actual independent storage.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_publication_mirror_history import (
        verify as verify_history, _decode, MAX_ARCHIVE,
        SnapshotHistoryConflict,
    )
    from .audit_record_witness_publication_mirror_witness import ROLES
    from .audit_record_witness_publication_mirror import MirrorConflict
except ImportError:
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_publication_mirror_history import (
        verify as verify_history, _decode, MAX_ARCHIVE,
        SnapshotHistoryConflict,
    )
    from audit_record_witness_publication_mirror_witness import ROLES
    from audit_record_witness_publication_mirror import MirrorConflict

SCHEMA = 'wild-arms-ps1-two-archive-signed-mirror-history-comparison-v1'


class ArchiveConflict(ValueError):
    """Two independently pinned, submitted signed archives disagree."""


def compare(a_path,a_count,a_head,b_path,b_count,b_head,
            raw_first,pin_first,tip_first,
            raw_second,pin_second,tip_second,
            public_a,public_a_pin,public_b,public_b_pin,*,scope):
    """Require both complete archives valid; report first mismatched epoch."""
    # Neither the caller nor the verifier may assume two archive paths
    # or SHA pins represent physically independent archival storage.
    verified = []
    for raw,pin,tip in ((raw_first,pin_first,tip_first),
                        (raw_second,pin_second,tip_second)):
        verified.append(verify_history(
            a_path,a_count,a_head,b_path,b_count,b_head,
            raw,pin,public_a,public_a_pin,public_b,public_b_pin,
            scope=scope,expected_latest_witness=tip))
    if verified[0]['mirror_event_count'] != verified[1]['mirror_event_count']:
        raise ArchiveConflict('individually validated archives disagree on event count')

    left = _decode(raw_first,pin_first)
    right = _decode(raw_second,pin_second)
    common = min(len(left),len(right))
    for index in range(common):
        for role in ROLES:
            if not hmac.compare_digest(
                    hashlib.sha256(left[index][role]).digest(),
                    hashlib.sha256(right[index][role]).digest()):
                raise ArchiveConflict(
                    'conflicting validly signed history at submitted epoch '+str(index))
    if len(left) != len(right):
        raise ArchiveConflict('one submitted signed history has missing epoch')
    if not hmac.compare_digest(tip_first,tip_second):
        raise ArchiveConflict('submitted histories have different latest witness pins')
    return {
        'schema':SCHEMA,
        'both_signed_archives_individually_verified':True,
        'all_submitted_signed_epochs_identical':True,
        'complete_signed_rounds_compared':len(left),
        'separate_archive_storage_proved':False,
        'all_conflicting_signed_archives_discovered':False,
        'externally_enrolled_tips_are_globally_latest_proved':False,
        'synchronized_old_archives_and_old_pins_excluded':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mirror_a',type=Path)
    p.add_argument('mirror_b',type=Path)
    p.add_argument('first_history',type=Path)
    p.add_argument('first_history_sha256')
    p.add_argument('second_history',type=Path)
    p.add_argument('second_history_sha256')
    for side in ('a','b'):
        p.add_argument('--'+side+'-count',type=int,required=True)
        p.add_argument('--'+side+'-head',required=True)
        p.add_argument('--admin-'+side+'-public',type=Path,required=True)
        p.add_argument('--admin-'+side+'-public-pin',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--first-latest-witness-sha256',required=True)
    p.add_argument('--second-latest-witness-sha256',required=True)
    args=p.parse_args(argv)
    result={'schema':SCHEMA,'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        read=lambda path:_read_limited(_private_regular_file(path),MAX_ARCHIVE)
        result.update(compare(
            args.mirror_a,args.a_count,args.a_head,
            args.mirror_b,args.b_count,args.b_head,
            read(args.first_history),args.first_history_sha256,
            args.first_latest_witness_sha256,
            read(args.second_history),args.second_history_sha256,
            args.second_latest_witness_sha256,
            args.admin_a_public,args.admin_a_public_pin,
            args.admin_b_public,args.admin_b_public_pin,scope=args.scope))
        status=0
    except (ArchiveConflict,SnapshotHistoryConflict,MirrorConflict,ValueError):
        result['submitted_signed_archive_conflict_or_invalidity']=True
        status=1
    except (OSError,sqlite3.Error,TypeError,KeyError,IndexError):
        result['valid_input']=False
        status=2
    print(json.dumps(result,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
