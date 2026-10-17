"""Hash-bind two private PS1 snapshot streams to a temporal claim and EXE.

Raw-file SHA-256 integrity and internal agreement never authenticate
the emulator, debugger, capture device, timestamps or genuine PS1 execution.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    from .audit_record_temporal_slot_snapshots import analyze as audit_temporal
    from .audit_record_global_slot_witness import read_raw_iso_entry
    from .audit_record_executed_access_claims import MAX_REFERENCE_BYTES
except ImportError:
    from audit_record_temporal_slot_snapshots import analyze as audit_temporal
    from audit_record_global_slot_witness import read_raw_iso_entry
    from audit_record_executed_access_claims import MAX_REFERENCE_BYTES

SCHEMA = 'wild-arms-ps1-capture-stream-binding-v1'
REPORT_SCHEMA = 'wild-arms-ps1-capture-stream-audit-v1'
MAX_STREAM_BYTES = 128 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
MAX_ENTRIES = 96
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_TAG = re.compile(r'[A-Za-z0-9_-]{1,32}\Z')
_ROW_FIELDS = frozenset({
    'session_tag', 'site', 'record_index', 'execution_tag',
    'at_pc_u32', 'slot_address_u32', 'slot_word_u32',
    'event_sequence', 'collector_tag',
})
_SNAPSHOT_FIELDS = frozenset({
    'at_pc_u32', 'slot_address_u32', 'slot_word_u32',
    'event_sequence', 'collector_tag',
})


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate private JSON field')
        result[key] = value
    return result


def _parse(raw):
    if type(raw) is not bytes:
        raise ValueError('non-byte private input')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_strict_pairs)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(text):
    if type(text) is not str or not _SHA.fullmatch(text):
        raise ValueError('invalid private digest')
    return text


def _tag(value):
    if type(value) is not str or not _TAG.fullmatch(value):
        raise ValueError('invalid private stream/session tag')
    return value


def _rows(raw, *, session, collector, expected_count):
    if not 0 < len(raw) <= MAX_STREAM_BYTES or not raw.endswith(b'\n'):
        raise ValueError('invalid bounded private JSONL stream')
    lines = raw.split(b'\n')[:-1]
    if len(lines) != expected_count or not 1 <= len(lines) <= MAX_ENTRIES:
        raise ValueError('incorrect private stream row count')
    seen = set()
    result = {}
    previous_seq = -1
    for line in lines:
        if not line or len(line) > 4096:
            raise ValueError('invalid bounded private JSONL entry')
        row = _parse(line)
        if type(row) is not dict or set(row) != _ROW_FIELDS:
            raise ValueError('unexpected private JSONL entry fields')
        if (row['session_tag'] != session
                or row['collector_tag'] != collector
                or type(row['site']) is not str
                or type(row['record_index']) is not int
                or not 0 <= row['record_index'] <= 65535):
            raise ValueError('invalid private JSONL row metadata')
        _tag(row['execution_tag'])
        seq = row['event_sequence']
        if type(seq) is not int or not 0 <= seq <= 0xffffffff:
            raise ValueError('invalid private JSONL sequence')
        if seq <= previous_seq:
            raise ValueError('unordered/reused private stream event')
        previous_seq = seq
        key = (row['site'], row['record_index'])
        if key in seen:
            raise ValueError('duplicated site/index in private stream')
        seen.add(key)
        result[key] = row
    return result


def analyze(exe, temporal_raw, manifest_raw, before_raw, after_raw):
    """Validate digests AND all nested, untrusted snapshot relationships.

    Files are never modified. Successful cryptographic digests prove only
    that supplied bytes equal supplied digest values.
    """
    # Existing bounded PS-X EXE readers and synthetic fixtures may
    # return a bytearray; hash it byte-for-byte without reserialization.
    # The four private evidence artifacts must be immutable raw bytes.
    if (type(exe) not in (bytes, bytearray)
            or any(type(raw) is not bytes for raw in
                   (temporal_raw, manifest_raw, before_raw, after_raw))):
        raise ValueError('unexpected private input types')
    if (not 0 < len(temporal_raw) <= MAX_REFERENCE_BYTES
            or not 0 < len(manifest_raw) <= MAX_MANIFEST_BYTES):
        raise ValueError('oversized private claim/manifest')
    manifest = _parse(manifest_raw)
    if (type(manifest) is not dict or set(manifest) != {
            'schema', 'session_tag', 'exe_sha256',
            'temporal_claim_sha256', 'streams'}
            or manifest['schema'] != SCHEMA):
        raise ValueError('invalid manifest schema')
    session = _tag(manifest['session_tag'])
    if (_digest(manifest['exe_sha256']) != _sha(exe)
            or _digest(manifest['temporal_claim_sha256']) != _sha(temporal_raw)):
        raise ValueError('digest mismatch for supplied private EXE/claim')
    entries = manifest['streams']
    if type(entries) is not list or len(entries) != 2:
        raise ValueError('expected exactly two private capture streams')
    stream_info = {}
    for entry in entries:
        if (type(entry) is not dict or set(entry) != {
                'role', 'collector_tag', 'sha256'}
                or type(entry['role']) is not str
                or entry['role'] not in ('before', 'after')
                or entry['role'] in stream_info):
            raise ValueError('invalid private capture stream metadata')
        stream_info[entry['role']] = {
            'collector': _tag(entry['collector_tag']),
            'sha256': _digest(entry['sha256']),
        }
    if (set(stream_info) != {'before', 'after'}
            or stream_info['before']['collector']
            == stream_info['after']['collector']):
        raise ValueError('not two distinct claimed collector labels')
    if (_sha(before_raw) != stream_info['before']['sha256']
            or _sha(after_raw) != stream_info['after']['sha256']
            or _sha(before_raw) == _sha(after_raw)):
        raise ValueError('private capture stream digest mismatch')

    temporal = _parse(temporal_raw)
    # This also checks EXE SHA inside temporal's nested stage-236 claim.
    prior = audit_temporal(exe, temporal)
    windows = temporal['read_windows']
    if type(windows) is not list or not 1 <= len(windows) <= MAX_ENTRIES:
        raise ValueError('invalid temporal capture window count')
    before = _rows(before_raw, session=session,
                   collector=stream_info['before']['collector'],
                   expected_count=len(windows))
    after = _rows(after_raw, session=session,
                  collector=stream_info['after']['collector'],
                  expected_count=len(windows))
    wanted = {(row['site'], row['record_index']): row for row in windows}
    if (len(wanted) != len(windows)
            or set(wanted) != set(before) or set(wanted) != set(after)):
        raise ValueError('private stream coverage mismatch')

    matched = 0
    for key, window in wanted.items():
        x, y = before[key], after[key]
        if (x['execution_tag'] != window['execution_tag']
                or y['execution_tag'] != window['execution_tag']):
            continue
        valid = True
        for role, row in (('before', x), ('after', y)):
            snapshot = window[role]
            if (type(snapshot) is not dict
                    or set(snapshot) != _SNAPSHOT_FIELDS):
                raise ValueError('invalid temporal snapshot schema')
            for field in _SNAPSHOT_FIELDS:
                if row[field] != snapshot[field]:
                    valid = False
                    break
        if valid:
            matched += 1
    return {
        'schema': REPORT_SCHEMA,
        'input_sha256_integrity_checked': True,
        'exe_image_digest_matched': True,
        'temporal_claim_digest_matched': True,
        'distinct_claimed_capture_streams': 2,
        'claimed_stream_rows_checked': len(before) + len(after),
        'claimed_window_pairs_checked': len(wanted),
        'stream_pairs_matching_temporal_claim': matched,
        'prior_temporal_slot_claims_consistent':
            prior['all_claimed_temporal_snapshots_consistent'],
        'all_supplied_stream_claims_consistent': bool(
            prior['all_claimed_temporal_snapshots_consistent']
            and matched == len(wanted)),
        'collection_origin_independently_authenticated': False,
        'raw_memory_observation_authenticated': False,
        'original_ps1_execution_verified': False,
        'original_game_record_size_verified': False,
        'native_switch_game_build_verified': False,
        'private_hashes_addresses_or_values_emitted': False,
    }


def _read_limited(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('oversized private input')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('temporal_claim', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('before_stream', type=Path)
    parser.add_argument('after_stream', type=Path)
    args = parser.parse_args(argv)
    try:
        entries = json.loads(args.inventory.read_text(encoding='utf-8'))['entries']
        found = [row for row in entries if type(row) is dict
                 and row.get('path') == '/EXE/WILDARMS.EXE;1'
                 and not row.get('directory', False)]
        if len(found) != 1:
            raise ValueError('expected exactly one original EXE entry')
        exe = read_raw_iso_entry(args.disc, found[0])
        result = analyze(
            exe, _read_limited(args.temporal_claim, MAX_REFERENCE_BYTES),
            _read_limited(args.manifest, MAX_MANIFEST_BYTES),
            _read_limited(args.before_stream, MAX_STREAM_BYTES),
            _read_limited(args.after_stream, MAX_STREAM_BYTES))
    except (OSError, ValueError, UnicodeError, TypeError,
            KeyError, IndexError, OverflowError, RecursionError):
        print(json.dumps({
            'schema': REPORT_SCHEMA, 'valid_input': False,
            'error_code': 'invalid_private_input',
            'private_hashes_addresses_or_values_emitted': False},
            sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result['all_supplied_stream_claims_consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
