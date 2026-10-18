"""Stage 263M: read-only two-admin checkpoint for an independent replay journal.

Verify two DISTINCT pinned Ed25519 signers over the same journal head and
predecessor anchor, plus an externally retained digest of BOTH signed files.
No signing keys are used here. Signatures attest to HEAD CLAIMS ONLY:
a replayed old DB together with an old signed checkpoint can still pass
when the externally retained latest pin is also rolled back. No unlock API.
"""
import argparse
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import re

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_witness_run_replay_ledger import (
        SCHEMA as LEDGER_SCHEMA, _private_path, _connect, _audit, MAX_EVENTS,
    )
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import _private_regular_file
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_witness_run_replay_ledger import (
        SCHEMA as LEDGER_SCHEMA, _private_path, _connect, _audit, MAX_EVENTS,
    )
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import _private_regular_file

SCHEMA = 'wild-arms-ps1-two-admin-replay-head-claim-v1'
DOMAIN = b'wild-arms-ps1-two-admin-replay-head-claim-v1\x00'
ANCHOR_DOMAIN = b'wild-arms-ps1-two-admin-replay-head-anchor-v1\x00'
REPORT_SCHEMA = 'wild-arms-ps1-two-admin-replay-head-audit-v1'
ANCHOR_GENESIS = hashlib.sha256(ANCHOR_DOMAIN + b'genesis').hexdigest()
MAX_SIGNED = 3072
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
TAG = re.compile(r'[A-Za-z0-9_.:-]{1,96}\Z')
FIELDS = {
    'schema', 'admin_role', 'checkpoint_tag', 'ledger_schema',
    'ledger_count', 'ledger_head_sha256', 'prior_checkpoint_sha256',
    'checkpoint_nonce', 'witness_fence_retirement_authorized',
}


class CheckpointConflict(ValueError):
    """Untrusted signer, mismatched head, reused checkpoint or stale pin."""


def _hex(value, regex):
    if type(value) is not str or not regex.fullmatch(value):
        raise CheckpointConflict('invalid independently retained digest or nonce')
    return value


def make_body(role, count, head, prior, nonce, tag):
    """Deterministic unsigned template for independent offline Ed25519 signing."""
    if role not in ('admin-a', 'admin-b'):
        raise CheckpointConflict('unknown required independent signer role')
    if type(count) is not int or not 0 <= count <= MAX_EVENTS:
        raise CheckpointConflict('invalid replay journal event count')
    _hex(head, HEX64)
    _hex(prior, HEX64)
    _hex(nonce, HEX32)
    if type(tag) is not str or not TAG.fullmatch(tag):
        raise CheckpointConflict('invalid trusted checkpoint scope tag')
    if count == 0 and head != hashlib.sha256(
            b'wild-arms-ps1-observer-run-replay-ledger-v1\x00genesis').hexdigest():
        raise CheckpointConflict('incorrect signed genesis ledger head')
    return {
        'schema': SCHEMA,
        'admin_role': role,
        'checkpoint_tag': tag,
        'ledger_schema': LEDGER_SCHEMA,
        'ledger_count': count,
        'ledger_head_sha256': head,
        'prior_checkpoint_sha256': prior,
        'checkpoint_nonce': nonce,
        'witness_fence_retirement_authorized': False,
    }


def checkpoint_digest(signed_a, signed_b):
    """Compute a candidate anchor; trust ONLY externally escrowed result."""
    if (type(signed_a) is not bytes or type(signed_b) is not bytes
            or not 0 < len(signed_a) <= MAX_SIGNED
            or not 0 < len(signed_b) <= MAX_SIGNED):
        raise CheckpointConflict('invalid signed checkpoint file')
    item = {
        'schema': SCHEMA,
        'admin_a_signed_sha256': hashlib.sha256(signed_a).hexdigest(),
        'admin_b_signed_sha256': hashlib.sha256(signed_b).hexdigest(),
    }
    return hashlib.sha256(ANCHOR_DOMAIN + _canonical(item)).hexdigest()


def verify(journal_path, signed_a, signed_b, public_a, public_a_pin,
           public_b, public_b_pin, *, checkpoint_tag, prior_checkpoint_pin,
           independently_pinned_checkpoint_sha256):
    """Verify both signatures and independently pinned head under journal lock."""
    a_pin = _hex(public_a_pin, HEX64)
    b_pin = _hex(public_b_pin, HEX64)
    prior = _hex(prior_checkpoint_pin, HEX64)
    expected = _hex(independently_pinned_checkpoint_sha256, HEX64)
    if hmac.compare_digest(a_pin, b_pin):
        raise CheckpointConflict('admin signing keys are not independent')
    # Verify the cryptographic statements BEFORE opening the private journal.
    a = _signed(signed_a, SCHEMA, DOMAIN, a_pin, public_a)
    b = _signed(signed_b, SCHEMA, DOMAIN, b_pin, public_b)
    if (type(a) is not dict or type(b) is not dict
            or set(a) != FIELDS or set(b) != FIELDS):
        raise CheckpointConflict('unexpected signed journal head fields')
    for role, body in (('admin-a', a), ('admin-b', b)):
        if body != make_body(
                role, body['ledger_count'], body['ledger_head_sha256'],
                body['prior_checkpoint_sha256'],
                body['checkpoint_nonce'], body['checkpoint_tag']):
            raise CheckpointConflict('unsafe or malformed signed journal head')
    if (a['checkpoint_tag'] != checkpoint_tag or
            b['checkpoint_tag'] != checkpoint_tag or
            a['prior_checkpoint_sha256'] != prior or
            b['prior_checkpoint_sha256'] != prior or
            {k: v for k, v in a.items() if k != 'admin_role'} !=
            {k: v for k, v in b.items() if k != 'admin_role'}):
        raise CheckpointConflict('admin head claims differ or ignore previous anchor')
    candidate = checkpoint_digest(signed_a, signed_b)
    if not hmac.compare_digest(candidate, expected):
        raise CheckpointConflict('checkpoint differs from independent latest pin')
    path = _private_path(journal_path, exists=True)
    with closing(_connect(path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            count,head,_,_ = _audit(con)
            if count != a['ledger_count'] or not hmac.compare_digest(
                    head, a['ledger_head_sha256']):
                raise CheckpointConflict('journal rolled back or differs from signed head')
        finally:
            con.rollback()
    return {
        'schema': REPORT_SCHEMA,
        'two_distinct_admin_ed25519_head_claims_valid': True,
        'signed_journal_head_matches_readonly_audit': True,
        'checkpoint_matches_external_latest_pin': True,
        'signed_predecessor_anchor_matches_pin': True,
        'checkpoint_event_count': count,
        'checkpoint_sha256': candidate,
        'continuous_external_head_escrow_proved': False,
        'historical_replay_with_old_pins_excluded': False,
        'hardware_backed_rollback_prevention_proved': False,
        'tool_execution_independently_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_replay_journal', type=Path)
    parser.add_argument('admin_a_signed_head', type=Path)
    parser.add_argument('admin_a_public_key', type=Path)
    parser.add_argument('admin_a_public_pin')
    parser.add_argument('admin_b_signed_head', type=Path)
    parser.add_argument('admin_b_public_key', type=Path)
    parser.add_argument('admin_b_public_pin')
    parser.add_argument('--checkpoint-tag', required=True)
    parser.add_argument('--prior-checkpoint-sha256', required=True)
    parser.add_argument('--latest-checkpoint-sha256', required=True)
    args = parser.parse_args(argv)
    result = {
        'schema': REPORT_SCHEMA,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
    }
    try:
        a = _read_limited(_private_regular_file(args.admin_a_signed_head), MAX_SIGNED)
        b = _read_limited(_private_regular_file(args.admin_b_signed_head), MAX_SIGNED)
        result.update(verify(
            args.private_replay_journal, a, b,
            args.admin_a_public_key, args.admin_a_public_pin,
            args.admin_b_public_key, args.admin_b_public_pin,
            checkpoint_tag=args.checkpoint_tag,
            prior_checkpoint_pin=args.prior_checkpoint_sha256,
            independently_pinned_checkpoint_sha256=args.latest_checkpoint_sha256))
        code = 0
    except CheckpointConflict:
        result['signed_checkpoint_or_journal_conflict'] = True
        code = 1
    except (ValueError, OSError, TypeError, KeyError,
            UnicodeError, IndexError):
        result['valid_input'] = False
        code = 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
