"""Stage 263Q: local append-only-by-API intake of signed escrow publications.

Each signed operator receipt is published separately. A first, valid
receipt is recorded once. Conflicting *validly signed* receipts are logged
as irreversible local conflict evidence rather than replacing first seen
claims; after conflict, further publication is blocked. Both ledger
and accepted registry require separately pinned heads.

This is a local SQLite research prototype, not independent remote
publication, a global transparency log, rollback-proof storage, proof
of actual operator identity, or an authorization to release a fence.
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
    from .audit_record_witness_run_replay_ledger import _private_path
    from .audit_record_witness_checkpoint_registry import (
        _connect, _audit as _registry_audit,
        _check_registry_pin, GENESIS as REGISTRY_GENESIS,
        RegistryConflict,
    )
    from .audit_record_witness_replay_head_checkpoint import (
        ANCHOR_GENESIS, _public_key_identity,
    )
    from .audit_record_witness_escrow_quorum import (
        SCHEMA as CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN,
        PIN_DOMAIN as ESCROW_PIN_DOMAIN, ESCROW_GENESIS,
        FIELDS as CLAIM_FIELDS, ROLES, HEX64, TAG, MAX_SIGNED,
        make_body,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_run_replay_ledger import _private_path
    from audit_record_witness_checkpoint_registry import (
        _connect, _audit as _registry_audit,
        _check_registry_pin, GENESIS as REGISTRY_GENESIS,
        RegistryConflict,
    )
    from audit_record_witness_replay_head_checkpoint import (
        ANCHOR_GENESIS, _public_key_identity,
    )
    from audit_record_witness_escrow_quorum import (
        SCHEMA as CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN,
        PIN_DOMAIN as ESCROW_PIN_DOMAIN, ESCROW_GENESIS,
        FIELDS as CLAIM_FIELDS, ROLES, HEX64, TAG, MAX_SIGNED,
        make_body,
    )

SCHEMA = 'wild-arms-ps1-local-escrow-publication-intake-v1'
REPORT_SCHEMA = 'wild-arms-ps1-local-escrow-publication-intake-report-v1'
DOMAIN = b'wild-arms-ps1-local-escrow-publication-intake-v1\x00'
GENESIS = hashlib.sha256(DOMAIN+b'genesis').hexdigest()
MARKER = 0x50554251  # PUBQ
MAX_RECORDS = 96
COLUMNS = (
    'sequence','schema','prior_event_sha256','scope','round_number','role',
    'signed_receipt_sha256','signer_key_material_sha256',
    'registry_head_sha256','checkpoint_sha256',
    'previous_escrow_sha256','round_nonce','decision','reason',
    'original_receipt_sha256','event_sha256',
)
CREATE_SQL = """CREATE TABLE published_escrow_receipts (
    sequence INTEGER PRIMARY KEY,
    schema TEXT NOT NULL,
    prior_event_sha256 TEXT NOT NULL,
    scope TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    role TEXT NOT NULL,
    signed_receipt_sha256 TEXT NOT NULL,
    signer_key_material_sha256 TEXT NOT NULL,
    registry_head_sha256 TEXT NOT NULL,
    checkpoint_sha256 TEXT NOT NULL,
    previous_escrow_sha256 TEXT NOT NULL,
    round_nonce TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    original_receipt_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL
)"""
CONFLICT_REASONS = {
    'slot-conflict','peer-conflict','registry-conflict',
    'prior-conflict','gap-conflict','nonce-conflict',
}


class PublicationConflict(ValueError):
    """Replay, tampered registry or conflict-frozen local publication ledger."""


def _sha(value):
    if type(value) is not str or not HEX64.fullmatch(value):
        raise PublicationConflict('invalid independently pinned SHA-256')
    return value


def _status(count, head, conflict, *, decision=None, initialized=False):
    return {
        'schema': REPORT_SCHEMA,
        'intake_event_count': count,
        'intake_head_sha256': head,
        'new_intake_created': initialized,
        'new_receipt_accepted': decision == 'accepted',
        'signed_conflict_recorded': decision == 'conflict',
        'intake_frozen_by_conflict': conflict,
        'complete_remote_publication_proved': False,
        'all_equivocations_discovered': False,
        'independent_latest_head_storage_proved': False,
        'rollback_prevention_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def _audit(con):
    if con.execute('PRAGMA user_version').fetchone()[0] != MARKER:
        raise PublicationConflict('publication intake header changed')
    objects = con.execute(
        "SELECT type,name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if objects != [('table','published_escrow_receipts', CREATE_SQL)]:
        raise PublicationConflict('unexpected table, trigger, index or view')
    columns = tuple(r[1] for r in
                    con.execute('PRAGMA table_info(published_escrow_receipts)'))
    if columns != COLUMNS:
        raise PublicationConflict('publication intake columns changed')
    rows = con.execute('SELECT '+','.join(COLUMNS)+' FROM '
                       'published_escrow_receipts ORDER BY sequence').fetchall()
    if len(rows) > MAX_RECORDS:
        raise PublicationConflict('intake exceeds audited event bound')
    previous = GENESIS
    accepted = {}
    frozen = False
    scope = None
    for n, raw in enumerate(rows, 1):
        r = dict(zip(COLUMNS,raw))
        fields = {k:r[k] for k in COLUMNS[:-1]}
        if (type(r['sequence']) is not int or r['sequence'] != n
                or r['schema'] != SCHEMA
                or r['prior_event_sha256'] != previous
                or type(r['scope']) is not str
                or not TAG.fullmatch(r['scope'])
                or (scope is not None and scope != r['scope'])
                or type(r['round_number']) is not int
                or not 0 <= r['round_number'] <= MAX_RECORDS//3
                or r['role'] not in ROLES
                or type(r['round_nonce']) is not str
                or len(r['round_nonce']) != 32
                or any(c not in '0123456789abcdef'
                       for c in r['round_nonce'])
                or any(not (type(r[k]) is str and HEX64.fullmatch(r[k]))
                       for k in ('signed_receipt_sha256',
                                 'signer_key_material_sha256',
                                 'registry_head_sha256',
                                 'checkpoint_sha256','previous_escrow_sha256',
                                 'original_receipt_sha256','event_sha256'))
                or (r['decision'],r['reason']) not in (
                    {('accepted','none')}
                    | {('conflict',reason) for reason in CONFLICT_REASONS})
                or frozen
                or not hmac.compare_digest(hashlib.sha256(
                    DOMAIN+_canonical(fields)).hexdigest(),r['event_sha256'])):
            raise PublicationConflict('tampered or inconsistent publication chain')
        slot = (r['round_number'],r['role'])
        if r['decision'] == 'accepted':
            if slot in accepted or r['original_receipt_sha256'] != '0'*64:
                raise PublicationConflict('duplicate accepted publication')
            if any(
                    (old['role'] != r['role']
                     and old['signer_key_material_sha256'] ==
                     r['signer_key_material_sha256'])
                    or (old['role'] == r['role']
                        and old['signer_key_material_sha256'] !=
                        r['signer_key_material_sha256'])
                    for old in accepted.values()):
                raise PublicationConflict('operator signing key enrollment changed')
            accepted[slot] = r
        else:
            if r['reason'] == 'slot-conflict':
                if (slot not in accepted
                        or r['original_receipt_sha256'] !=
                        accepted[slot]['signed_receipt_sha256']
                        or r['signed_receipt_sha256'] ==
                        r['original_receipt_sha256']):
                    raise PublicationConflict('invalid recorded duplicate conflict')
            elif r['original_receipt_sha256'] != '0'*64:
                raise PublicationConflict('unexpected original conflict commitment')
            frozen = True
        previous = r['event_sha256']
        scope = r['scope']
    return len(rows), previous, accepted, frozen, scope


def initialize(path):
    path = _private_path(path, exists=False)
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                 getattr(os,'O_NOFOLLOW',0), 0o600)
    os.close(fd)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(CREATE_SQL)
            con.execute('PRAGMA user_version='+str(MARKER))
            con.commit()
            if _audit(con)[:2] != (0,GENESIS):
                raise PublicationConflict('new intake genesis differs')
        except Exception:
            con.rollback()
            raise
    return _status(0,GENESIS,False,initialized=True)


def _expect(count,head,expected_count,expected_head):
    _sha(expected_head)
    if (type(expected_count) is not int or count != expected_count
            or not hmac.compare_digest(head,expected_head)):
        raise PublicationConflict('local intake differs from independent latest pin')


def inspect(path,expected_count,expected_head):
    path = _private_path(path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count,head,_,conflict,_ = _audit(con)
            _expect(count,head,expected_count,expected_head)
        finally:
            con.rollback()
    return _status(count,head,conflict)


def _candidate(raw, role, public_path, public_pin, scope):
    if role not in ROLES:
        raise PublicationConflict('unrecognized escrow role')
    _sha(public_pin)
    if type(scope) is not str or not TAG.fullmatch(scope):
        raise PublicationConflict('invalid enrolled publication scope')
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SIGNED:
        raise PublicationConflict('invalid signed receipt length')
    claim = _signed(raw,CLAIM_SCHEMA,CLAIM_DOMAIN,public_pin,public_path)
    if type(claim) is not dict or set(claim) != CLAIM_FIELDS:
        raise PublicationConflict('unexpected operator claim fields')
    if claim != make_body(
            role,claim['registry_event_count'],claim['registry_head_sha256'],
            claim['latest_checkpoint_sha256'],claim['previous_escrow_sha256'],
            claim['escrow_round_nonce'],claim['checkpoint_tag']):
        raise PublicationConflict('unsafe signed escrow claim')
    if claim['checkpoint_tag'] != scope:
        raise PublicationConflict('unrecognized publication scope')
    return claim


def _registry_state(path,expected_count,expected_head,expected_checkpoint):
    _sha(expected_checkpoint)
    path = _private_path(path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count,head,checkpoint,_,scope,_ = _registry_audit(con)
            _check_registry_pin(count,head,expected_count,expected_head)
            if not hmac.compare_digest(checkpoint,expected_checkpoint):
                raise PublicationConflict('external accepted-checkpoint tip differs')
            rows = con.execute(
                'SELECT sequence,event_sha256,checkpoint_sha256,checkpoint_tag '
                'FROM accepted_replay_checkpoints ORDER BY sequence').fetchall()
        finally:
            con.rollback()
    return count,scope,{seq:(eh,ch,tag) for seq,eh,ch,tag in rows}


def _round_bundle(accepted,number):
    if not all((number,role) in accepted for role in ROLES):
        return None
    items = {role:accepted[(number,role)]['signed_receipt_sha256']
             for role in ROLES}
    return hashlib.sha256(ESCROW_PIN_DOMAIN+_canonical({
        'schema':CLAIM_SCHEMA,'signed_receipts':items})).hexdigest()


def submit(intake_path, registry_path, signed_raw,role,
           public_path,public_pin, *, checkpoint_tag,
           expected_intake_count,expected_intake_head,
           expected_registry_count,expected_registry_head,
           expected_registry_checkpoint):
    """Signatures checked before atomic log; a conflict event is committed."""
    claim = _candidate(signed_raw,role,public_path,public_pin,checkpoint_tag)
    number = claim['registry_event_count']
    if number > MAX_RECORDS//3:
        raise PublicationConflict('publication history exceeds bound')
    if Path(intake_path).resolve() == Path(registry_path).resolve():
        raise PublicationConflict('independent intake must not alias registry')
    count,registry_scope, registry_events = _registry_state(
        registry_path,expected_registry_count,expected_registry_head,
        expected_registry_checkpoint)
    if number > count or (registry_scope is not None and
                          registry_scope != checkpoint_tag):
        raise PublicationConflict('publication exceeds pinned accepted registry')

    registry_head,checkpoint = (
        (REGISTRY_GENESIS,ANCHOR_GENESIS) if number == 0
        else registry_events[number][:2]
    )
    signed_hash = hashlib.sha256(signed_raw).hexdigest()
    key_material = _public_key_identity(public_path).hex()
    intake_path = _private_path(intake_path, exists=True)
    with closing(_connect(intake_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            n,head,accepted,frozen,scope = _audit(con)
            _expect(n,head,expected_intake_count,expected_intake_head)
            if frozen:
                raise PublicationConflict('publication intake frozen by signed conflict')
            if scope is not None and scope != checkpoint_tag:
                raise PublicationConflict('published scope differs')
            if n >= MAX_RECORDS:
                raise PublicationConflict('publication intake exceeds bound')
            if any(
                    (old['role'] != role and
                     old['signer_key_material_sha256'] == key_material)
                    or (old['role'] == role and
                        old['signer_key_material_sha256'] != key_material)
                    for old in accepted.values()):
                raise PublicationConflict('duplicated or rotated operator key')
            slot = (number,role)
            previous = accepted.get(slot)
            if previous is not None and previous['signed_receipt_sha256'] == signed_hash:
                raise PublicationConflict('exact signed receipt already published')
            reason = None
            if previous is not None:
                reason = 'slot-conflict'
            elif (claim['registry_head_sha256'] != registry_head
                  or claim['latest_checkpoint_sha256'] != checkpoint):
                reason = 'registry-conflict'
            elif number and (prior := _round_bundle(accepted,number-1)) is None:
                reason = 'gap-conflict'
            elif claim['previous_escrow_sha256'] != (
                    ESCROW_GENESIS if number == 0 else prior):
                reason = 'prior-conflict'
            else:
                peers = [accepted[(number,p)] for p in ROLES
                         if (number,p) in accepted]
                if peers and any(
                    (claim['escrow_round_nonce'] != p['round_nonce']
                     or claim['previous_escrow_sha256'] !=
                     p['previous_escrow_sha256']) for p in peers):
                    reason = 'peer-conflict'
                elif any(
                    r['round_nonce'] == claim['escrow_round_nonce']
                    for (num,_),r in accepted.items() if num != number):
                    reason = 'nonce-conflict'
            conflict = reason is not None
            event = {
                'sequence':n+1,'schema':SCHEMA,
                'prior_event_sha256':head,
                'scope':checkpoint_tag,'round_number':number,'role':role,
                'signed_receipt_sha256':signed_hash,
                'signer_key_material_sha256':key_material,
                'registry_head_sha256':claim['registry_head_sha256'],
                'checkpoint_sha256':claim['latest_checkpoint_sha256'],
                'previous_escrow_sha256':claim['previous_escrow_sha256'],
                'round_nonce':claim['escrow_round_nonce'],
                'decision':'conflict' if conflict else 'accepted',
                'reason':reason if conflict else 'none',
                'original_receipt_sha256':(
                    previous['signed_receipt_sha256'] if previous else '0'*64),
            }
            digest = hashlib.sha256(DOMAIN+_canonical(event)).hexdigest()
            con.execute(
                'INSERT INTO published_escrow_receipts VALUES '
                '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (*event.values(),digest))
            updated=_audit(con)
            if (updated[0] != n+1 or updated[1] != digest or
                    updated[3] != conflict):
                raise PublicationConflict('publication event not atomically verified')
            con.commit()
        except Exception:
            con.rollback()
            raise
    return _status(n+1,digest,conflict,decision=event['decision'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest='action',required=True)
    p=modes.add_parser('init')
    p.add_argument('private_intake',type=Path)
    p=modes.add_parser('inspect')
    p.add_argument('private_intake',type=Path)
    p.add_argument('--expected-count',type=int,required=True)
    p.add_argument('--expected-head',required=True)
    p=modes.add_parser('submit')
    p.add_argument('private_intake',type=Path)
    p.add_argument('accepted_registry',type=Path)
    p.add_argument('signed_receipt',type=Path)
    p.add_argument('escrow_role',choices=ROLES)
    p.add_argument('pinned_public_key',type=Path)
    p.add_argument('pinned_public_sha256')
    p.add_argument('--checkpoint-tag',required=True)
    p.add_argument('--expected-count',type=int,required=True)
    p.add_argument('--expected-head',required=True)
    p.add_argument('--expected-registry-count',type=int,required=True)
    p.add_argument('--expected-registry-head',required=True)
    p.add_argument('--expected-checkpoint',required=True)
    args=parser.parse_args(argv)
    output={'schema':REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False}
    try:
        if args.action=='init':
            result=initialize(args.private_intake)
        elif args.action=='inspect':
            result=inspect(args.private_intake,args.expected_count,
                           args.expected_head)
        else:
            raw=_read_limited(_private_regular_file(args.signed_receipt),
                              MAX_SIGNED)
            result=submit(
                args.private_intake,args.accepted_registry,raw,
                args.escrow_role,args.pinned_public_key,
                args.pinned_public_sha256,
                checkpoint_tag=args.checkpoint_tag,
                expected_intake_count=args.expected_count,
                expected_intake_head=args.expected_head,
                expected_registry_count=args.expected_registry_count,
                expected_registry_head=args.expected_registry_head,
                expected_registry_checkpoint=args.expected_checkpoint)
        output.update(result)
        code=1 if result['signed_conflict_recorded'] else 0
    except (PublicationConflict,RegistryConflict):
        output['publication_rejected'] = True
        code=1
    except (OSError,ValueError,TypeError,KeyError,IndexError,sqlite3.Error):
        output['valid_input']=False
        code=2
    print(json.dumps(output,sort_keys=True))
    return code


if __name__=='__main__':
    raise SystemExit(main())
