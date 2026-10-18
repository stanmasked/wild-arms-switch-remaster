"""Stage 263P: signed escrow history continuity, completeness and equivocation.

Require signed three-operator receipts for *every* accepted Stage 263N
checkpoint, including the genesis round. Compare each claimed registry
head with the corresponding hash-chain event, and link all successive
escrow bundle digests. Optionally compare a second independently pinned
archive. This is local retrospective validation, NOT discovery of hidden
archive branches or independent storage attestation. No fence release.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_replay_head_checkpoint import _public_key_identity
    from .audit_record_witness_checkpoint_registry import (
        _private_path, _connect, _audit, _check_registry_pin,
        GENESIS as REGISTRY_GENESIS, RegistryConflict,
    )
    from .audit_record_witness_replay_head_checkpoint import ANCHOR_GENESIS
    from .audit_record_witness_escrow_quorum import (
        SCHEMA as CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN, ROLES,
        FIELDS as CLAIM_FIELDS, ESCROW_GENESIS, MAX_SIGNED,
        TAG, HEX64, make_body, bundle_digest,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_replay_head_checkpoint import (
        _public_key_identity, ANCHOR_GENESIS,
    )
    from audit_record_witness_checkpoint_registry import (
        _private_path, _connect, _audit, _check_registry_pin,
        GENESIS as REGISTRY_GENESIS, RegistryConflict,
    )
    from audit_record_witness_escrow_quorum import (
        SCHEMA as CLAIM_SCHEMA, DOMAIN as CLAIM_DOMAIN, ROLES,
        FIELDS as CLAIM_FIELDS, ESCROW_GENESIS, MAX_SIGNED,
        TAG, HEX64, make_body, bundle_digest,
    )

SCHEMA = 'wild-arms-ps1-three-operator-escrow-history-v1'
REPORT_SCHEMA = 'wild-arms-ps1-three-operator-escrow-history-audit-v1'
MAX_ROUNDS = 32
MAX_HISTORY = 650000


class HistoryConflict(ValueError):
    """Broken, truncated, conflicting or untrusted escrow history."""


def _pin(value):
    if type(value) is not str or not HEX64.fullmatch(value):
        raise HistoryConflict('missing or invalid independent SHA-256 pin')
    return value


def pack(rounds):
    """Build canonical PRIVATE archive from exact signed envelope bytes."""
    if (type(rounds) is not list or not 0 < len(rounds) <= MAX_ROUNDS):
        raise HistoryConflict('invalid bounded escrow round count')
    items = []
    for receipts in rounds:
        if type(receipts) is not dict or set(receipts) != set(ROLES):
            raise HistoryConflict('one complete three-operator round required')
        row = {}
        for role in ROLES:
            content = receipts[role]
            if type(content) is not bytes or not 0 < len(content) <= MAX_SIGNED:
                raise HistoryConflict('oversized or empty signed operator receipt')
            row[role] = content.hex()
        items.append(row)
    raw = _canonical({'schema': SCHEMA, 'rounds': items})
    if len(raw) > MAX_HISTORY:
        raise HistoryConflict('signed receipt archive exceeds size limit')
    return raw


def _decode(raw, pin):
    _pin(pin)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_HISTORY:
        raise HistoryConflict('invalid bounded escrow history file')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), pin):
        raise HistoryConflict('history file differs from independent pin')

    def unique_keys(pairs):
        item = {}
        for key, value in pairs:
            if key in item:
                raise HistoryConflict('duplicate escrow JSON key')
            item[key] = value
        return item

    try:
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError) as exc:
        raise HistoryConflict('invalid history JSON') from exc
    if (type(data) is not dict or set(data) != {'schema', 'rounds'}
            or data['schema'] != SCHEMA or type(data['rounds']) is not list
            or not 0 < len(data['rounds']) <= MAX_ROUNDS
            or raw != _canonical(data)):
        raise HistoryConflict('noncanonical or incomplete escrow history')
    rounds = []
    for item in data['rounds']:
        if type(item) is not dict or set(item) != set(ROLES):
            raise HistoryConflict('incomplete or unknown signed round role')
        parsed = {}
        for role in ROLES:
            hexed = item[role]
            if (type(hexed) is not str or not 0 < len(hexed) <= MAX_SIGNED*2
                    or len(hexed) % 2
                    or any(ch not in '0123456789abcdef' for ch in hexed)):
                raise HistoryConflict('invalid encoded signed receipt')
            parsed[role] = bytes.fromhex(hexed)
        rounds.append(parsed)
    return rounds


def _verify_keys(public_paths, public_pins):
    if (type(public_paths) is not dict or set(public_paths) != set(ROLES)
            or type(public_pins) is not dict or set(public_pins) != set(ROLES)):
        raise HistoryConflict('all three enrolled operator keys required')
    key_material = set()
    pin_set = set()
    for role in ROLES:
        value = _pin(public_pins[role])
        if value in pin_set:
            raise HistoryConflict('duplicated operator public key hash')
        pin_set.add(value)
        der = _public_key_identity(public_paths[role])
        if der in key_material:
            raise HistoryConflict('duplicate key with different PEM encoding')
        key_material.add(der)


def _walk(rounds, registry_events, public_paths, public_pins, *,
          scope, external_latest_escrow):
    if len(rounds) != len(registry_events)+1:
        raise HistoryConflict('missing intermediate or additional escrow round')
    prior = ESCROW_GENESIS
    used_nonces = set()
    hashes = []
    for index, receipts in enumerate(rounds):
        if index == 0:
            event_head, checkpoint = REGISTRY_GENESIS, ANCHOR_GENESIS
        else:
            event = registry_events[index-1]
            if event['sequence'] != index or event['checkpoint_tag'] != scope:
                raise HistoryConflict('registry history event identity changed')
            event_head = event['event_sha256']
            checkpoint = event['checkpoint_sha256']
        bodies = []
        for role in ROLES:
            body = _signed(receipts[role], CLAIM_SCHEMA, CLAIM_DOMAIN,
                           public_pins[role], public_paths[role])
            if type(body) is not dict or set(body) != CLAIM_FIELDS:
                raise HistoryConflict('unexpected signed history claim fields')
            if body != make_body(
                    role, index, event_head, checkpoint, prior,
                    body['escrow_round_nonce'], scope):
                raise HistoryConflict('signed escrow round or prior head differs')
            bodies.append(body)
        for body in bodies[1:]:
            if {k:v for k,v in body.items() if k != 'escrow_role'} != {
                    k:v for k,v in bodies[0].items() if k != 'escrow_role'}:
                raise HistoryConflict('operators signed conflicting round history')
        nonce = bodies[0]['escrow_round_nonce']
        if nonce in used_nonces:
            raise HistoryConflict('reused three-operator history nonce')
        used_nonces.add(nonce)
        prior = bundle_digest(receipts)
        hashes.append(prior)
    if not hmac.compare_digest(prior, external_latest_escrow):
        raise HistoryConflict('latest signed history tip differs from escrow pin')
    return hashes


def verify(registry_path, history_raw, history_pin, public_paths,
           public_pins, *, checkpoint_tag, expected_registry_count,
           expected_registry_head, expected_latest_checkpoint,
           expected_latest_escrow, comparison_raw=None, comparison_pin=None):
    """Require a complete, signed round 0..N for every accepted registry event."""
    if type(checkpoint_tag) is not str or not TAG.fullmatch(checkpoint_tag):
        raise HistoryConflict('invalid externally pinned escrow scope')
    for value in (expected_registry_head, expected_latest_checkpoint,
                  expected_latest_escrow):
        _pin(value)
    if (type(expected_registry_count) is not int
            or expected_registry_count < 0
            or expected_registry_count >= MAX_ROUNDS):
        raise HistoryConflict('accepted registry count exceeds history bound')
    if (comparison_raw is None) != (comparison_pin is None):
        raise HistoryConflict('comparison archive and pin must be supplied together')
    _verify_keys(public_paths, public_pins)
    rounds = _decode(history_raw, history_pin)
    comparison = (_decode(comparison_raw, comparison_pin)
                  if comparison_raw is not None else None)

    registry_path = _private_path(registry_path, exists=True)
    with closing(_connect(registry_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count,head,checkpoint,_,scope,_ = _audit(con)
            _check_registry_pin(
                count,head,expected_registry_count,expected_registry_head)
            if (not hmac.compare_digest(checkpoint, expected_latest_checkpoint)
                    or (scope is not None and scope != checkpoint_tag)):
                raise HistoryConflict('current accepted registry tip differs')
            rows = con.execute(
                'SELECT sequence,event_sha256,checkpoint_sha256,checkpoint_tag '
                'FROM accepted_replay_checkpoints ORDER BY sequence'
            ).fetchall()
            events = [dict(zip(
                ('sequence','event_sha256','checkpoint_sha256','checkpoint_tag'),
                row)) for row in rows]
            if len(events) != count:
                raise HistoryConflict('registry changed during snapshot')
        finally:
            con.rollback()

    signed_round_hashes = _walk(
        rounds,events,public_paths,public_pins,scope=checkpoint_tag,
        external_latest_escrow=expected_latest_escrow)
    if comparison is not None:
        other_hashes = _walk(
            comparison,events,public_paths,public_pins,scope=checkpoint_tag,
            external_latest_escrow=expected_latest_escrow)
        if other_hashes != signed_round_hashes:
            raise HistoryConflict('independently pinned archives equivocate')
    return {
        'schema': REPORT_SCHEMA,
        'signed_complete_registry_rounds_verified': True,
        'signed_genesis_and_all_successors_checked': True,
        'every_accepted_checkpoint_has_exactly_one_archive_round': True,
        'signed_rounds': len(rounds),
        'registry_event_count': count,
        'latest_escrow_bundle_sha256': signed_round_hashes[-1],
        'two_submitted_archives_consistent': comparison is not None,
        'independent_physical_archive_storage_proved': False,
        'all_conflicting_archives_discovered': False,
        'continuous_escrow_latest_tip_proved': False,
        'old_registry_plus_old_external_pins_excluded': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_registry', type=Path)
    parser.add_argument('private_history', type=Path)
    parser.add_argument('history_sha256')
    parser.add_argument('--checkpoint-tag', required=True)
    parser.add_argument('--expected-count', type=int, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--expected-checkpoint', required=True)
    parser.add_argument('--latest-escrow-sha256', required=True)
    parser.add_argument('--comparison-history', type=Path)
    parser.add_argument('--comparison-sha256')
    for role in ROLES:
        parser.add_argument('--'+role+'-public', type=Path, required=True)
        parser.add_argument('--'+role+'-public-sha256', required=True)
    args = parser.parse_args(argv)
    report = {
        'schema': REPORT_SCHEMA, 'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
    }
    try:
        def read(path):
            return _read_limited(_private_regular_file(path), MAX_HISTORY)
        report.update(verify(
            args.private_registry, read(args.private_history),
            args.history_sha256,
            {role: getattr(args, role.replace('-','_')+'_public')
             for role in ROLES},
            {role: getattr(args, role.replace('-','_')+'_public_sha256')
             for role in ROLES},
            checkpoint_tag=args.checkpoint_tag,
            expected_registry_count=args.expected_count,
            expected_registry_head=args.expected_head,
            expected_latest_checkpoint=args.expected_checkpoint,
            expected_latest_escrow=args.latest_escrow_sha256,
            comparison_raw=(read(args.comparison_history)
                            if args.comparison_history else None),
            comparison_pin=args.comparison_sha256))
        code = 0
    except (HistoryConflict, RegistryConflict):
        report['incomplete_or_conflicting_escrow_history'] = True
        code = 1
    except (ValueError, OSError, TypeError, KeyError, IndexError, sqlite3.Error):
        report['valid_input'] = False
        code = 2
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
