"""Stage 263T — complete dual-signed mirror snapshot succession (read-only).

Require epoch 0 (genesis) and one Ed25519 two-admin checkpoint per
subsequent Stage 263Q publication event. Bind each checkpoint to the
event's historical SHA-256, the prefix's conflict-frozen state and
the *previous pair of full signed witness envelopes*. Verify two
separately pinned local SQLite journals under concurrent read locks.

This is NOT a secure independent publication service or trusted
globally monotonic storage. Old valid journals, signed archives AND
old external pins remain a replay threat. No fence-release API.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import _public_key_identity
    from .audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, COLUMNS,
        GENESIS as INTAKE_GENESIS,
    )
    from .audit_record_witness_publication_mirror import MirrorConflict
    from .audit_record_witness_publication_mirror_witness import (
        SCHEMA as WITNESS_SCHEMA, DOMAIN as WITNESS_DOMAIN,
        ROLES, FIELDS, WITNESS_GENESIS, MAX_SIGNED,
        make_body, witness_digest,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import _public_key_identity
    from audit_record_witness_publication_intake import (
        _private_path, _connect, _audit, _expect, COLUMNS,
        GENESIS as INTAKE_GENESIS,
    )
    from audit_record_witness_publication_mirror import MirrorConflict
    from audit_record_witness_publication_mirror_witness import (
        SCHEMA as WITNESS_SCHEMA, DOMAIN as WITNESS_DOMAIN,
        ROLES, FIELDS, WITNESS_GENESIS, MAX_SIGNED,
        make_body, witness_digest,
    )

SCHEMA = 'wild-arms-ps1-signed-mirror-snapshot-history-v1'
REPORT_SCHEMA = 'wild-arms-ps1-signed-mirror-snapshot-history-audit-v1'
MAX_ROUNDS = 32  # genesis plus at most 31 publication events
MAX_ARCHIVE = 420000


class SnapshotHistoryConflict(ValueError):
    """An incomplete, tampered, stale or internally conflicting signed archive."""


def _hex64(value):
    if (type(value) is not str or len(value) != 64
            or any(ch not in '0123456789abcdef' for ch in value)):
        raise SnapshotHistoryConflict('invalid independently retained SHA-256')
    return value


def pack(rounds):
    """Pack *exact* two-role signed envelope bytes, without normalizing them."""
    if type(rounds) is not list or not 0 < len(rounds) <= MAX_ROUNDS:
        raise SnapshotHistoryConflict('invalid number of signed mirror rounds')
    out = []
    for claims in rounds:
        if type(claims) is not dict or set(claims) != set(ROLES):
            raise SnapshotHistoryConflict('incomplete mirror snapshot round')
        entry = {}
        for role in ROLES:
            raw = claims[role]
            if type(raw) is not bytes or not 0 < len(raw) <= MAX_SIGNED:
                raise SnapshotHistoryConflict('invalid bounded signed mirror claim')
            entry[role] = raw.hex()
        out.append(entry)
    encoded = _canonical({'schema': SCHEMA, 'rounds':out})
    if len(encoded) > MAX_ARCHIVE:
        raise SnapshotHistoryConflict('signed mirror history exceeds size bound')
    return encoded


def _decode(raw, pin):
    _hex64(pin)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARCHIVE:
        raise SnapshotHistoryConflict('invalid private signed history bytes')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), pin):
        raise SnapshotHistoryConflict('signed history differs from independent pin')

    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise SnapshotHistoryConflict('duplicate signed history JSON key')
            result[k] = v
        return result

    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise SnapshotHistoryConflict('malformed signed history JSON') from exc
    if (type(obj) is not dict or set(obj) != {'schema','rounds'}
            or obj['schema'] != SCHEMA or type(obj['rounds']) is not list
            or not 0 < len(obj['rounds']) <= MAX_ROUNDS
            or raw != _canonical(obj)):
        raise SnapshotHistoryConflict('noncanonical or incomplete signed archive')
    result = []
    for claim in obj['rounds']:
        if type(claim) is not dict or set(claim) != set(ROLES):
            raise SnapshotHistoryConflict('unknown or missing signed mirror role')
        row = {}
        for role in ROLES:
            value = claim[role]
            if (type(value) is not str or not 0 < len(value) <= MAX_SIGNED*2
                    or len(value) % 2
                    or any(ch not in '0123456789abcdef' for ch in value)):
                raise SnapshotHistoryConflict('invalid signed envelope encoding')
            row[role] = bytes.fromhex(value)
        result.append(row)
    return result


def _two_mirror_snapshot(a_path, a_count, a_head, b_path, b_count, b_head):
    """Hold both SQLite read snapshots for same-time local reconciliation."""
    a = _private_path(a_path, exists=True)
    b = _private_path(b_path, exists=True)
    ast = os.stat(a,follow_symlinks=False)
    bst = os.stat(b,follow_symlinks=False)
    if (ast.st_dev,ast.st_ino) == (bst.st_dev,bst.st_ino):
        raise MirrorConflict('same SQLite inode cannot be two archives')
    with closing(_connect(a)) as ca, closing(_connect(b)) as cb:
        ca.execute('BEGIN IMMEDIATE')
        try:
            cb.execute('BEGIN IMMEDIATE')
            try:
                snapshots = []
                for con,expected_count,expected_head in (
                        (ca,a_count,a_head),(cb,b_count,b_head)):
                    count,head,_,frozen,scope = _audit(con)
                    _expect(count,head,expected_count,expected_head)
                    rows = con.execute(
                        'SELECT '+','.join(COLUMNS)+
                        ' FROM published_escrow_receipts ORDER BY sequence'
                    ).fetchall()
                    if len(rows) != count:
                        raise SnapshotHistoryConflict('journal mutated within lock')
                    snapshots.append((tuple(rows),frozen,scope))
                if snapshots[0] != snapshots[1]:
                    raise MirrorConflict('two independently pinned journals diverge')
                return snapshots[0][0], snapshots[0][1]
            finally:
                cb.rollback()
        finally:
            ca.rollback()


def verify(a_path,a_count,a_head,b_path,b_count,b_head,archive_raw,archive_pin,
           public_a,public_a_pin,public_b,public_b_pin, *,
           scope, expected_latest_witness):
    """Verify complete epoch-by-epoch claims of both pinned history replicas."""
    _hex64(expected_latest_witness)
    _hex64(public_a_pin)
    _hex64(public_b_pin)
    if public_a_pin == public_b_pin or hmac.compare_digest(
            _public_key_identity(public_a),_public_key_identity(public_b)):
        raise SnapshotHistoryConflict('independent administrators share signing key')
    claims = _decode(archive_raw,archive_pin)
    events,frozen = _two_mirror_snapshot(
        a_path,a_count,a_head,b_path,b_count,b_head)
    if len(claims) != len(events)+1:
        raise SnapshotHistoryConflict('missing intermediate mirror witness epoch')
    if len(claims) > MAX_ROUNDS:
        raise SnapshotHistoryConflict('too many signed mirror epochs')

    prior = WITNESS_GENESIS
    used_nonces = set()
    freeze_prefix = False
    for epoch,signed in enumerate(claims):
        if epoch:
            item = dict(zip(COLUMNS,events[epoch-1]))
            event_head = item['event_sha256']
            if item['decision'] == 'conflict':
                freeze_prefix = True
        else:
            event_head = INTAKE_GENESIS
        bodies = []
        for role,raw,key,pin in (
                (ROLES[0],signed[ROLES[0]],public_a,public_a_pin),
                (ROLES[1],signed[ROLES[1]],public_b,public_b_pin)):
            body = _signed(raw,WITNESS_SCHEMA,WITNESS_DOMAIN,pin,key)
            if type(body) is not dict or set(body) != FIELDS:
                raise SnapshotHistoryConflict('unexpected signed mirror claim fields')
            expected = make_body(
                role,epoch,epoch,event_head,freeze_prefix,prior,
                body['witness_nonce'],scope)
            if body != expected:
                raise SnapshotHistoryConflict('incorrect signed epoch or ancestor')
            bodies.append(body)
        if bodies[0]['witness_nonce'] != bodies[1]['witness_nonce']:
            raise SnapshotHistoryConflict('admin mirror epoch nonces disagree')
        nonce = bodies[0]['witness_nonce']
        if nonce in used_nonces:
            raise SnapshotHistoryConflict('reused mirror witness epoch nonce')
        used_nonces.add(nonce)
        prior = witness_digest(signed)
    if not hmac.compare_digest(prior,expected_latest_witness):
        raise SnapshotHistoryConflict('latest signed mirror epoch differs from pin')
    if len(events) and freeze_prefix != frozen:
        raise SnapshotHistoryConflict('conflict freeze state changed')
    return {
        'schema':REPORT_SCHEMA,
        'signed_genesis_and_all_mirror_event_epochs_verified': True,
        'both_mirror_chains_match_complete_signed_history': True,
        'signed_epoch_count':len(claims),
        'mirror_event_count':len(events),
        'latest_witness_sha256':prior,
        'independent_physical_storage_proved':False,
        'trusted_global_monotonic_counter_proved':False,
        'old_complete_history_with_old_pins_excluded':False,
        'all_hidden_equivocations_discovered':False,
        'witness_fence_retirement_authorized':False,
        'witness_fence_retired':False,
        'native_switch_game_build_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mirror_a',type=Path)
    p.add_argument('mirror_b',type=Path)
    p.add_argument('private_history',type=Path)
    p.add_argument('history_sha256')
    for role in ('a','b'):
        p.add_argument('--'+role+'-count',type=int,required=True)
        p.add_argument('--'+role+'-head',required=True)
        p.add_argument('--admin-'+role+'-public',type=Path,required=True)
        p.add_argument('--admin-'+role+'-public-pin',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--latest-witness-sha256',required=True)
    args=p.parse_args(argv)
    answer={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        raw=_read_limited(_private_regular_file(args.private_history),MAX_ARCHIVE)
        answer.update(verify(
            args.mirror_a,args.a_count,args.a_head,
            args.mirror_b,args.b_count,args.b_head,raw,args.history_sha256,
            args.admin_a_public,args.admin_a_public_pin,
            args.admin_b_public,args.admin_b_public_pin,
            scope=args.scope,expected_latest_witness=args.latest_witness_sha256))
        code=0
    except (SnapshotHistoryConflict,MirrorConflict,ValueError):
        answer['incomplete_or_conflicting_mirror_witnesses']=True
        code=1
    except (OSError,sqlite3.Error,TypeError,KeyError,IndexError):
        answer['valid_input']=False
        code=2
    print(json.dumps(answer,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())
