"""Stage 263J: privacy-preserving, fail-closed composite witness evidence.

Compose exact signed stop/request/cgroup evidence and EIGHT canonical,
successful-but-nonauthorizing observation reports. Hash their unmodified
bytes, preserve explicit session binding and publish a domain-separated
manifest. Verify requires the complete sources AND an independently retained
manifest SHA-256. Unauthenticated reports are not magically attested,
simultaneous, or a basis for retiring any witness fence.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path

try:
    from .audit_record_anchor_handoff import _canonical
    from .audit_record_capture_stream_binding import _read_limited
    from .audit_record_verifier_checkpoint import (
        _private_regular_file, _write_new_private,
    )
    from .audit_record_witness_fence_reconciliation import (
        _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from .audit_record_witness_fence_quiescence import (
        _verified_stop, MAX_STOP,
    )
    from .audit_record_witness_fence import _owner
    from .audit_record_witness_linux_quiescence import (
        SCHEMA as CGROUP_SCHEMA, MAX_EVIDENCE,
        evidence_sha256 as cgroup_evidence_sha256,
    )
except ImportError:
    from audit_record_anchor_handoff import _canonical
    from audit_record_capture_stream_binding import _read_limited
    from audit_record_verifier_checkpoint import (
        _private_regular_file, _write_new_private,
    )
    from audit_record_witness_fence_reconciliation import (
        _original, _request_digest, MAX_ORIGINAL_REQUEST,
    )
    from audit_record_witness_fence_quiescence import _verified_stop, MAX_STOP
    from audit_record_witness_fence import _owner
    from audit_record_witness_linux_quiescence import (
        SCHEMA as CGROUP_SCHEMA, MAX_EVIDENCE,
        evidence_sha256 as cgroup_evidence_sha256,
    )

SCHEMA = 'wild-arms-ps1-witness-composite-evidence-v1'
REPORT_SCHEMA = 'wild-arms-ps1-witness-composite-audit-report-v1'
DOMAIN = b'wild-arms-ps1-witness-composite-evidence-v1\x00'
MAX_REPORT = 4096
MAX_BUNDLE = 8192
_HEX = set('0123456789abcdef')

# Every report key is required, and no additional key is accepted. True means
# "the specific bounded check was positive", NEVER "global stop is proved".
# False means the reporting tool explicitly withheld an unsafe assertion.
SPECS = {
    'preflight': (
        'wild-arms-ps1-witness-abort-preflight-report-v1',
        ('signed_external_stop_claim_verified',
         'negative_state_observed_under_sqlite_writer_lock'),
        ('external_process_quiescence_independently_proved',
         'all_writer_entrypoints_durably_disabled',
         'fence_retirement_authorized', 'fence_retired',
         'original_ps1_execution_verified', 'native_switch_game_build_verified',
         'private_tokens_or_keys_emitted'),
        ('negative_snapshot_classification',),
    ),
    'quarantine': (
        'wild-arms-ps1-custodian-write-quarantine-report-v1',
        ('custody_writer_quarantine_installed', 'instrumented_writers_blocked'),
        ('external_process_quiescence_independently_proved',
         'all_entrypoints_durably_disabled', 'witness_fence_retired',
         'safe_to_reconcile_negative_outcome',
         'native_switch_game_build_verified', 'private_credentials_emitted'),
        ('negative_snapshot_classification',),
    ),
    'cgroup': (
        'wild-arms-ps1-linux-cgroup-quiescence-report-v1',
        ('signed_supervisor_claim_binds_observed_cgroup',
         'enrolled_boot_and_cgroup_identity_match',
         'frozen_and_empty_at_observation'),
        ('external_writer_revocation_proved',
         'all_possible_writer_processes_excluded',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'production_quiescence_proved', 'native_switch_game_build_verified'),
        (),
    ),
    'revocation': (
        'wild-arms-ps1-linux-writer-revocation-report-v1',
        ('systemd_unit_masked_and_inactive_at_observation',
         'enrolled_service_uid_denied_by_basic_file_modes',
         'signed_cgroup_snapshot_reverified'),
        ('alternate_processes_or_privileged_writers_excluded',
         'durable_global_writer_revocation_proved',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'production_quiescence_proved', 'native_switch_game_build_verified'),
        ('observation_sha256',),
    ),
    'binary': (
        'wild-arms-ps1-linux-writer-inventory-report-v1',
        ('bounded_procfs_scan_completed_twice',),
        ('known_writer_executables_observed_running',
         'enrolled_sqlite_objects_observed_open',
         'all_possible_writer_processes_excluded',
         'alternate_namespaces_or_database_copies_excluded',
         'continuous_writer_revocation_proved',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'native_switch_game_build_verified'),
        ('observation_sha256',),
    ),
    'interpreted': (
        'wild-arms-ps1-linux-interpreted-writer-report-v1',
        ('known_binary_and_fd_inventory_passed',
         'interpreter_process_scan_completed_twice'),
        ('enrolled_python_interpreters_observed_live',
         'unenrolled_python_versions_excluded',
         'unknown_script_and_module_writers_excluded',
         'argv_authenticity_proved', 'future_writer_restart_excluded',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'native_switch_game_build_verified'),
        ('observation_sha256',),
    ),
    'launchers': (
        'wild-arms-ps1-linux-alternative-launcher-report-v1',
        ('native_and_python_inventory_passed',
         'alternative_launcher_procfs_scanned_twice'),
        ('enrolled_alternative_launchers_observed',
         'known_script_or_module_argv_observed',
         'all_alternative_runtimes_excluded',
         'argv_is_authenticated_provenance', 'future_writer_launch_prevented',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'native_switch_game_build_verified'),
        ('observation_sha256',),
    ),
    'activation': (
        'wild-arms-ps1-systemd-activation-observation-v1',
        ('enrolled_service_masked_and_inactive',
         'enrolled_activation_units_masked_and_inactive',
         'all_enrolled_activation_units_checked_twice',
         'unregistered_observed_trigger_edges_rejected'),
        ('activation_graph_complete_proved',
         'unlisted_systemd_generators_excluded',
         'future_activation_prevented',
         'witness_fence_retirement_authorized', 'witness_fence_retired',
         'native_switch_game_build_verified'),
        ('observation_sha256',),
    ),
}
NEGATIVE_CLASSES = {
    'reservation-not-observed-in-snapshot',
    'checkpoint-not-committed-in-snapshot',
}


class CompositeConflict(ValueError):
    """Bad signed binding, partial report or inconsistent capture."""


def _hex64(value):
    return (type(value) is str and len(value) == 64
            and all(ch in _HEX for ch in value))


def _decode_canonical(raw, limit, description, *, allow_cli_format=False):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise CompositeConflict('invalid bounded '+description)
    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise CompositeConflict('duplicate JSON field in '+description)
            obj[key] = value
        return obj
    try:
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=no_duplicates)
    except (ValueError, UnicodeError) as exc:
        raise CompositeConflict('malformed '+description) from exc
    # Existing stage-263 CLIs emit json.dumps(..., sort_keys=True)
    # (with spaces); preserved verbatim, without weakening field checks.
    allowed = [_canonical(data)]
    if allow_cli_format:
        allowed.append((json.dumps(data, sort_keys=True) + '\n').encode('ascii'))
    if type(data) is not dict or raw not in allowed:
        raise CompositeConflict('noncanonical '+description)
    return data


def _report(key, raw):
    schema, positives, negatives, hashes = SPECS[key]
    result = _decode_canonical(raw, MAX_REPORT, key+' report',
                               allow_cli_format=True)
    expected = {'schema', *positives, *negatives, *hashes}
    if set(result) != expected or result['schema'] != schema:
        raise CompositeConflict('wrong or incomplete '+key+' report')
    if any(result[k] is not True for k in positives):
        raise CompositeConflict('bounded check failed in '+key+' report')
    if any(result[k] is not False for k in negatives):
        raise CompositeConflict('unsafe assertion in '+key+' report')
    for name in hashes:
        value = result[name]
        if name == 'observation_sha256':
            if not _hex64(value):
                raise CompositeConflict('invalid '+key+' observation digest')
        elif value not in NEGATIVE_CLASSES:
            raise CompositeConflict('invalid negative outcome class')
    return result


def build(original_raw, signed_stop_raw, cgroup_raw, reports,
          public_key, trusted_public_pin, *, supervisor_tag):
    """Bind supplied report BYTES to a signed, exact-request stop session."""
    if type(reports) is not dict or set(reports) != set(SPECS):
        raise CompositeConflict('missing, extra or duplicate evidence reports')
    request, _ = _original(original_raw)
    stop = _verified_stop(original_raw, signed_stop_raw, public_key,
                          trusted_public_pin, supervisor_tag)
    evidence = _decode_canonical(cgroup_raw, MAX_EVIDENCE, 'cgroup observation')
    if (set(evidence) != {
            'schema', 'custody_request_sha256', 'fence_owner_sha256',
            'stop_session_nonce', 'boot_id', 'scope', 'nodes'}
            or evidence['schema'] != CGROUP_SCHEMA
            or evidence['custody_request_sha256'] != _request_digest(original_raw)
            or evidence['fence_owner_sha256'] != _owner(request['request_id'])
            or evidence['stop_session_nonce'] != stop['stop_session_nonce']
            or cgroup_evidence_sha256(evidence) !=
            stop['control_evidence_sha256']
            or type(evidence['nodes']) is not list or not evidence['nodes']):
        raise CompositeConflict('signed stop and cgroup observation differ')

    parsed = {key: _report(key, reports[key]) for key in SPECS}
    if (parsed['preflight']['negative_snapshot_classification'] !=
            parsed['quarantine']['negative_snapshot_classification']):
        raise CompositeConflict('conflicting custody negative classifications')
    digests = {
        key: {'schema': SPECS[key][0],
              'report_sha256': hashlib.sha256(reports[key]).hexdigest(),
              **({'observation_sha256': parsed[key]['observation_sha256']}
                 if 'observation_sha256' in parsed[key] else {})}
        for key in SPECS
    }
    manifest = {
        'schema': SCHEMA,
        'session': {
            'original_request_sha256': _request_digest(original_raw),
            'signed_supervisor_stop_sha256': hashlib.sha256(
                signed_stop_raw).hexdigest(),
            'fence_owner_sha256': _owner(request['request_id']),
            'stop_session_nonce': stop['stop_session_nonce'],
            'cgroup_observation_sha256': hashlib.sha256(
                cgroup_raw).hexdigest(),
            'signed_cgroup_domain_sha256': stop['control_evidence_sha256'],
            'negative_snapshot_classification':
                parsed['preflight']['negative_snapshot_classification'],
        },
        'report_bindings': digests,
        'safety': {
            'reports_independently_attested': False,
            'reports_observed_atomically': False,
            'all_writers_durably_revoked': False,
            'witness_fence_retirement_authorized': False,
            'witness_fence_retired': False,
            'native_switch_game_build_verified': False,
        },
    }
    manifest['manifest_sha256'] = hashlib.sha256(
        DOMAIN + _canonical(manifest)).hexdigest()
    if len(_canonical(manifest)) > MAX_BUNDLE:
        raise CompositeConflict('composite manifest exceeds bound')
    return manifest


def verify(manifest_raw, independently_pinned_sha256, original_raw,
           signed_stop_raw, cgroup_raw, reports, public_key,
           trusted_public_pin, *, supervisor_tag):
    """Verification needs independently retained pin AND every source byte."""
    if not _hex64(independently_pinned_sha256):
        raise ValueError('missing independently pinned composite hash')
    manifest = _decode_canonical(manifest_raw, MAX_BUNDLE, 'composite manifest')
    if not hmac.compare_digest(
            hashlib.sha256(manifest_raw).hexdigest(),
            independently_pinned_sha256):
        raise CompositeConflict('composite differs from external whole-file pin')
    regenerated = build(original_raw, signed_stop_raw, cgroup_raw, reports,
                        public_key, trusted_public_pin,
                        supervisor_tag=supervisor_tag)
    if manifest_raw != _canonical(regenerated):
        raise CompositeConflict('reports, session or manifest changed')
    return {
        'schema': REPORT_SCHEMA,
        'independently_pinned_composite_file_matches': True,
        'original_and_signed_stop_bound': True,
        'all_eight_report_bytes_bound': True,
        'cross_report_negative_classification_matches': True,
        'report_authenticity_independently_proved': False,
        'observations_are_atomic': False,
        'all_writers_durably_revoked': False,
        'witness_fence_retirement_authorized': False,
        'witness_fence_retired': False,
        'native_switch_game_build_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('publish', 'verify'))
    parser.add_argument('original_private_request', type=Path)
    parser.add_argument('signed_supervisor_stop', type=Path)
    parser.add_argument('private_cgroup_observation', type=Path)
    parser.add_argument('pinned_supervisor_public_pem', type=Path)
    parser.add_argument('trusted_supervisor_public_sha256')
    parser.add_argument('private_composite_manifest', type=Path)
    parser.add_argument('--supervisor-tag', required=True)
    parser.add_argument('--expected-composite-sha256')
    for name in SPECS:
        parser.add_argument('--'+name+'-report', type=Path, required=True)
    args = parser.parse_args(argv)
    result = {'schema': REPORT_SCHEMA, 'witness_fence_retired': False,
              'witness_fence_retirement_authorized': False}
    try:
        original = _read_limited(
            _private_regular_file(args.original_private_request),
            MAX_ORIGINAL_REQUEST)
        stop = _read_limited(
            _private_regular_file(args.signed_supervisor_stop), MAX_STOP)
        cgroup = _read_limited(
            _private_regular_file(args.private_cgroup_observation),
            MAX_EVIDENCE)
        reports = {
            name: _read_limited(
                _private_regular_file(getattr(args, name+'_report')), MAX_REPORT)
            for name in SPECS
        }
        if args.mode == 'publish':
            if args.expected_composite_sha256 is not None:
                raise ValueError('published manifest cannot self-attest pin')
            manifest = build(
                original, stop, cgroup, reports,
                args.pinned_supervisor_public_pem,
                args.trusted_supervisor_public_sha256,
                supervisor_tag=args.supervisor_tag)
            raw = _canonical(manifest)
            _write_new_private(args.private_composite_manifest, raw)
            result['private_manifest_created'] = True
            result['whole_file_sha256_for_external_enrollment'] = (
                hashlib.sha256(raw).hexdigest())
        else:
            raw = _read_limited(
                _private_regular_file(args.private_composite_manifest),
                MAX_BUNDLE)
            result.update(verify(
                raw, args.expected_composite_sha256, original, stop,
                cgroup, reports, args.pinned_supervisor_public_pem,
                args.trusted_supervisor_public_sha256,
                supervisor_tag=args.supervisor_tag))
        code = 0
    except CompositeConflict as exc:
        result['report_or_session_binding_conflict'] = True
        # Every CompositeConflict has a static, non-sensitive reason string.
        # Never emit raw reports, session ids or private custody tokens.
        result['error_code'] = str(exc)
        code = 1
    except (OSError, ValueError, TypeError, UnicodeError, KeyError,
            json.JSONDecodeError):
        result['valid_input'] = False
        code = 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
