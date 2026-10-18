"""Stage 263K: verify external Ed25519 observation-origin attestations.

Each canonical report has a distinct signed operator run claim: report bytes,
source code bytes, external tool-inventory pin, composite session binding,
and an independently supplied run nonce. This authenticates OBSERVER CLAIMS,
not execution, OS quiescence, or complete writer revocation. No unlock API.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_witness_composite_evidence import (
        _decode_canonical, _report, DOMAIN as COMPOSITE_DOMAIN, SPECS,
        SCHEMA as COMPOSITE_SCHEMA,
        MAX_REPORT, MAX_BUNDLE, CompositeConflict,
    )
    from .audit_record_witness_fence_reconciliation import _signed
    from .audit_record_signed_custodian import _tag
    from .audit_record_verifier_checkpoint import _private_regular_file
    from .audit_record_capture_stream_binding import _read_limited
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_witness_composite_evidence import (
        _decode_canonical, SPECS, SCHEMA as COMPOSITE_SCHEMA,
        MAX_REPORT, MAX_BUNDLE, CompositeConflict,
    )
    from audit_record_witness_fence_reconciliation import _signed
    from audit_record_signed_custodian import _tag
    from audit_record_verifier_checkpoint import _private_regular_file
    from audit_record_capture_stream_binding import _read_limited

INDEX_SCHEMA = 'wild-arms-ps1-report-tool-source-index-v1'
CLAIM_SCHEMA = 'wild-arms-ps1-report-observer-run-claim-v1'
REPORT_SCHEMA = 'wild-arms-ps1-report-origin-verification-v1'
DOMAIN = b'wild-arms-ps1-report-observer-run-claim-v1\x00'
MAX_INDEX = 4096
MAX_TOOL_SOURCE = 65536
MAX_SIGNED = 2048
SHA = re.compile(r'[0-9a-f]{64}\Z')
NONCE = re.compile(r'[0-9a-f]{32}\Z')

TOOLS = {
    'preflight':'tools/audit_record_witness_fence_quiescence.py',
    'quarantine':'tools/audit_record_custodian_write_quarantine.py',
    'cgroup':'tools/audit_record_witness_linux_quiescence.py',
    'revocation':'tools/audit_record_linux_writer_revocation.py',
    'binary':'tools/audit_record_linux_writer_inventory.py',
    'interpreted':'tools/audit_record_linux_interpreted_writers.py',
    'launchers':'tools/audit_record_linux_launcher_inventory.py',
    'activation':'tools/audit_record_linux_activation_units.py',
}


class OriginConflict(CompositeConflict):
    """An enrolled tool, signed run, source report or session mismatches."""


def _digest(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise OriginConflict('invalid SHA-256 provenance pin')
    return value


def _index(raw, independently_pinned_sha256):
    if not _digest(independently_pinned_sha256):
        raise OriginConflict('missing external tool source index pin')
    if not hmac.compare_digest(
            hashlib.sha256(raw).hexdigest(), independently_pinned_sha256):
        raise OriginConflict('tool source index differs from independent pin')
    item = _decode_canonical(raw, MAX_INDEX, 'source provenance index')
    if (set(item) != {'schema','tools'}
            or item['schema'] != INDEX_SCHEMA
            or type(item['tools']) is not dict
            or set(item['tools']) != set(TOOLS)):
        raise OriginConflict('incomplete exact source code enrolment')
    for kind, entry in item['tools'].items():
        if (type(entry) is not dict or set(entry) != {'path','sha256'}
                or entry['path'] != TOOLS[kind]):
            raise OriginConflict('unexpected tool or source path')
        _digest(entry['sha256'])
    return item


def verify(composite_raw, composite_pin, index_raw, index_pin, reports,
           source_bytes, signed_runs, public_key, public_key_pin, *,
           observer_tag):
    """Verify all eight independently signed operator CLAIMS, never execution."""
    _digest(composite_pin)
    if not hmac.compare_digest(
            hashlib.sha256(composite_raw).hexdigest(), composite_pin):
        raise OriginConflict('composite manifest external pin mismatch')
    composite = _decode_canonical(composite_raw, MAX_BUNDLE, 'composite')
    if (composite.get('schema') != COMPOSITE_SCHEMA
            or set(composite) != {
                'schema','session','report_bindings','safety','manifest_sha256'}
            or type(composite['session']) is not dict
            or type(composite['report_bindings']) is not dict
            or set(composite['report_bindings']) != set(SPECS)
            or type(composite['safety']) is not dict
            or any(composite['safety'].get(x) is not False for x in (
                'reports_independently_attested',
                'reports_observed_atomically',
                'all_writers_durably_revoked',
                'witness_fence_retirement_authorized',
                'witness_fence_retired'))):
        raise OriginConflict('unsafe or incomplete upstream composite')
    # A verified external file pin alone does not mean the nested payload
    # satisfies the Stage 263J schema and internal domain hash contract.
    internal = dict(composite)
    claimed = internal.pop('manifest_sha256')
    if (type(claimed) is not str or not SHA.fullmatch(claimed)
            or not hmac.compare_digest(
                hashlib.sha256(
                    COMPOSITE_DOMAIN + _canonical(internal)).hexdigest(),
                claimed)):
        raise OriginConflict('composite internal manifest hash mismatch')
    if (set(composite['safety']) != {
            'reports_independently_attested','reports_observed_atomically',
            'all_writers_durably_revoked','witness_fence_retirement_authorized',
            'witness_fence_retired','native_switch_game_build_verified'}
            or composite['safety']['native_switch_game_build_verified'] is not False):
        raise OriginConflict('unexpected composite safety declarations')
    session = composite['session']
    if (not _digest(session.get('original_request_sha256'))
            or not _digest(session.get('signed_supervisor_stop_sha256'))
            or type(session.get('stop_session_nonce')) is not str
            or not NONCE.fullmatch(session['stop_session_nonce'])):
        raise OriginConflict('unbound signed original stop session')
    source_index = _index(index_raw, index_pin)
    if any(type(v) is not dict or set(v) != set(SPECS)
           for v in (reports,source_bytes,signed_runs)):
        raise OriginConflict('missing or unexpected observer proof')
    observed_nonces = set()
    for kind in SPECS:
        raw_report = reports[kind]
        try:
            _report(kind, raw_report)  # Exact Stage 263J report semantics.
        except CompositeConflict as exc:
            raise OriginConflict('report violates Stage 263J invariants') from exc
        if type(raw_report) is not bytes or len(raw_report) > MAX_REPORT:
            raise OriginConflict('oversized provenance report')
        bound = composite['report_bindings'][kind]
        if (type(bound) is not dict
                or bound.get('schema') != SPECS[kind][0]
                or not hmac.compare_digest(
                    hashlib.sha256(raw_report).hexdigest(),
                    _digest(bound.get('report_sha256')))):
            raise OriginConflict('report not found in pinned composite')
        source = source_bytes[kind]
        if (type(source) is not bytes or len(source) > MAX_TOOL_SOURCE
                or not hmac.compare_digest(
                    hashlib.sha256(source).hexdigest(),
                    source_index['tools'][kind]['sha256'])):
            raise OriginConflict('local analyzer code differs from external pin')
        claim = _signed(signed_runs[kind], CLAIM_SCHEMA, DOMAIN,
                        public_key_pin, public_key)
        expected_fields = {
            'schema','observer_tag','report_kind',
            'report_schema','report_sha256','source_path',
            'source_sha256','source_index_sha256','composite_sha256',
            'original_request_sha256','signed_stop_sha256',
            'stop_session_nonce','run_nonce',
        }
        if (type(claim) is not dict or set(claim) != expected_fields
                or claim['schema'] != CLAIM_SCHEMA
                or claim['observer_tag'] != _tag(observer_tag)
                or claim['report_kind'] != kind
                or claim['report_schema'] != SPECS[kind][0]
                or claim['report_sha256'] != bound['report_sha256']
                or claim['source_path'] != TOOLS[kind]
                or claim['source_sha256'] != source_index['tools'][kind]['sha256']
                or claim['source_index_sha256'] != index_pin
                or claim['composite_sha256'] != composite_pin
                or claim['original_request_sha256'] != session['original_request_sha256']
                or claim['signed_stop_sha256'] != session['signed_supervisor_stop_sha256']
                or claim['stop_session_nonce'] != session['stop_session_nonce']
                or type(claim['run_nonce']) is not str
                or not NONCE.fullmatch(claim['run_nonce'])
                or claim['run_nonce'] in observed_nonces):
            raise OriginConflict('observer run claim unbound or replayed in bundle')
        observed_nonces.add(claim['run_nonce'])
    return {
        'schema': REPORT_SCHEMA,
        'all_eight_observer_ed25519_claims_valid': True,
        'exact_report_bytes_and_tool_source_pinned': True,
        'all_claims_match_original_stop_session': True,
        'duplicate_run_nonces_within_bundle_rejected': True,
        'tool_execution_independently_proved': False,
        'observer_host_integrity_proved': False,
        'cross_run_replay_registry_enforced': False,
        'composite_reports_independently_attested_as_generated': False,
        'continuous_writer_revocation_proved': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('composite_private_manifest', type=Path)
    parser.add_argument('independent_composite_sha256')
    parser.add_argument('independent_source_index', type=Path)
    parser.add_argument('independent_source_index_sha256')
    parser.add_argument('pinned_observer_public_key', type=Path)
    parser.add_argument('pinned_observer_public_key_sha256')
    parser.add_argument('--observer-tag', required=True)
    for kind in SPECS:
        parser.add_argument('--'+kind+'-report', required=True, type=Path)
        parser.add_argument('--'+kind+'-tool-source', required=True, type=Path)
        parser.add_argument('--'+kind+'-signed-run', required=True, type=Path)
    args = parser.parse_args(argv)
    output = {'schema': REPORT_SCHEMA,
              'witness_fence_retirement_authorized': False,
              'witness_fence_retired': False}
    try:
        def read_private(path, limit):
            return _read_limited(_private_regular_file(path), limit)
        result = verify(
            read_private(args.composite_private_manifest, MAX_BUNDLE),
            args.independent_composite_sha256,
            read_private(args.independent_source_index, MAX_INDEX),
            args.independent_source_index_sha256,
            {k:read_private(getattr(args,k+'_report'), MAX_REPORT)
             for k in SPECS},
            {k:read_private(getattr(args,k+'_tool_source'), MAX_TOOL_SOURCE)
             for k in SPECS},
            {k:read_private(getattr(args,k+'_signed_run'), MAX_SIGNED)
             for k in SPECS},
            args.pinned_observer_public_key,
            args.pinned_observer_public_key_sha256,
            observer_tag=args.observer_tag)
        output.update(result)
        code = 0
    except OriginConflict:
        output['signed_origin_binding_conflict'] = True
        code = 1
    except (ValueError,OSError,TypeError,KeyError,UnicodeError):
        output['valid_input'] = False
        code = 2
    print(json.dumps(output,sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
