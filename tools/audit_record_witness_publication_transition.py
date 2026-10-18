"""Stage 263V — separately pinned signed-publication history transition audit.

A historical OLD pair of private publication journals and its two-admin
signed history must be an exact, strict prefix of a independently pinned
NEW pair and signed history. Each state is first fully audited using
Stage 263T. This is a read-only offline transition claim, not a trusted
globally monotonic latest head or evidence of remote physical escrow.
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
        verify as verify_history, _decode, _two_mirror_snapshot, MAX_ARCHIVE,
        SnapshotHistoryConflict,
    )
    from .audit_record_witness_publication_mirror_witness import ROLES
    from .audit_record_witness_publication_mirror import MirrorConflict
    from .audit_record_witness_publication_intake import COLUMNS, _private_path
except ImportError:
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_publication_mirror_history import (
        verify as verify_history, _decode, _two_mirror_snapshot, MAX_ARCHIVE,
        SnapshotHistoryConflict,
    )
    from audit_record_witness_publication_mirror_witness import ROLES
    from audit_record_witness_publication_mirror import MirrorConflict
    from audit_record_witness_publication_intake import COLUMNS, _private_path

SCHEMA = 'wild-arms-ps1-signed-publication-history-transition-v1'


class TransitionConflict(ValueError):
    """Submitted successor violates an independently pinned prior history."""


def _different_files(paths):
    import os
    identities = set()
    for path in paths:
        stat = os.stat(_private_path(path, exists=True),follow_symlinks=False)
        identity = (stat.st_dev,stat.st_ino)
        if identity in identities:
            raise TransitionConflict('old and new snapshots share SQLite inode')
        identities.add(identity)


def verify(old_a,old_b,old_count,old_head,old_archive,old_pin,old_tip,
           new_a,new_b,new_count,new_head,new_archive,new_pin,new_tip,
           public_a,public_a_pin,public_b,public_b_pin,*,scope):
    """Reject ambiguous equal, branched, frozen or backward transitions."""
    if (type(old_count) is not int or type(new_count) is not int
            or old_count < 0 or new_count <= old_count):
        raise TransitionConflict('transition must strictly advance event count')
    _different_files((old_a,old_b,new_a,new_b))
    for a,b,count,head,raw,pin,tip in (
            (old_a,old_b,old_count,old_head,old_archive,old_pin,old_tip),
            (new_a,new_b,new_count,new_head,new_archive,new_pin,new_tip)):
        verify_history(
            a,count,head,b,count,head,raw,pin,
            public_a,public_a_pin,public_b,public_b_pin,
            scope=scope,expected_latest_witness=tip)

    old_events,old_frozen = _two_mirror_snapshot(
        old_a,old_count,old_head,old_b,old_count,old_head)
    new_events,_ = _two_mirror_snapshot(
        new_a,new_count,new_head,new_b,new_count,new_head)
    if old_frozen:
        raise TransitionConflict('a conflict-frozen history must never advance')
    if old_events != new_events[:len(old_events)]:
        raise TransitionConflict('new publication history rewrote prior event')
    if len(new_events) <= len(old_events):
        raise TransitionConflict('new snapshot is not a strict journal successor')
    old_signed = _decode(old_archive,old_pin)
    new_signed = _decode(new_archive,new_pin)
    if len(new_signed) <= len(old_signed):
        raise TransitionConflict('new signed witnesses do not extend old history')
    for epoch,round_old in enumerate(old_signed):
        for role in ROLES:
            if not hmac.compare_digest(round_old[role],new_signed[epoch][role]):
                raise TransitionConflict(
                    'successor changed previously signed epoch '+str(epoch))
    # The pinned previous pair's full signed bytes must remain the exact
    # ancestor of the newly presented archive, never re-signed/overwritten.
    return {
        'schema':SCHEMA,
        'prior_and_successor_signed_histories_verified':True,
        'exact_published_event_prefix_preserved':True,
        'exact_signed_witness_epoch_prefix_preserved':True,
        'old_event_count':old_count,
        'new_event_count':new_count,
        'newly_added_events':new_count-old_count,
        'independently_trusted_latest_head_proved':False,
        'old_plus_new_pins_cannot_both_be_replayed_proved':False,
        'independent_physical_archival_custody_proved':False,
        'globally_discovered_equivocations_proved':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for version in ('old','new'):
        p.add_argument(version+'_mirror_a',type=Path)
        p.add_argument(version+'_mirror_b',type=Path)
        p.add_argument(version+'_history',type=Path)
        p.add_argument('--'+version+'-count',type=int,required=True)
        p.add_argument('--'+version+'-head',required=True)
        p.add_argument('--'+version+'-history-sha256',required=True)
        p.add_argument('--'+version+'-latest-witness-sha256',required=True)
    for admin in ('a','b'):
        p.add_argument('--admin-'+admin+'-public',type=Path,required=True)
        p.add_argument('--admin-'+admin+'-public-pin',required=True)
    p.add_argument('--scope',required=True)
    x=p.parse_args(argv)
    result={'schema':SCHEMA,'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        read=lambda path:_read_limited(_private_regular_file(path),MAX_ARCHIVE)
        result.update(verify(
            x.old_mirror_a,x.old_mirror_b,
            x.old_count,x.old_head,read(x.old_history),
            x.old_history_sha256,x.old_latest_witness_sha256,
            x.new_mirror_a,x.new_mirror_b,
            x.new_count,x.new_head,read(x.new_history),
            x.new_history_sha256,x.new_latest_witness_sha256,
            x.admin_a_public,x.admin_a_public_pin,
            x.admin_b_public,x.admin_b_public_pin,scope=x.scope))
        code=0
    except (TransitionConflict,SnapshotHistoryConflict,MirrorConflict,
            ValueError):
        result['invalid_or_conflicting_signed_transition']=True
        code=1
    except (OSError,sqlite3.Error,TypeError,KeyError,IndexError):
        result['valid_input']=False
        code=2
    print(json.dumps(result,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())
