"""Reserved capture acceptance with durable purpose-bound reservation intent."""
from contextlib import closing
import hashlib

try:
    from .audit_record_atomic_verifier import _connect
    from .audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES)
    from .audit_record_capture_stream_binding import _sha
    from .audit_record_guarded_admission import _now
    from .audit_record_receipt_gated_admission import _ready, accept_with_latest, AnchorConflict
    from .audit_record_remote_admission import _remote_head
    from .audit_record_remote_reserved_issue import _prepare
except ImportError:
    from audit_record_atomic_verifier import _connect
    from audit_record_capture_provenance import (
        analyze as audit_provenance, _json_object, MAX_PROVENANCE_BYTES)
    from audit_record_capture_stream_binding import _sha
    from audit_record_guarded_admission import _now
    from audit_record_receipt_gated_admission import _ready, accept_with_latest, AnchorConflict
    from audit_record_remote_admission import _remote_head
    from audit_record_remote_reserved_issue import _prepare


def evidence_digest(evidence):
    """Bind a reserved head to the exact eight length-delimited byte fields."""
    if len(evidence) != 8 or any(type(value) is not bytes for value in evidence):
        raise ValueError('invalid evidence bundle')
    checksum = hashlib.sha256(b'wild-arms-reserved-accept-evidence-v1\x00')
    for item in evidence:
        checksum.update(len(item).to_bytes(8, 'big'))
        checksum.update(item)
    return checksum.hexdigest()


def eligible(db_path, latest, evidence, *, now=None):
    """Check original evidence and nonce eligibility before remote reserve."""
    exe, temporal, binding, before, after, provenance, before_receipt, after_receipt = evidence
    report = audit_provenance(
        exe, temporal, binding, before, after, provenance, before_receipt, after_receipt)
    if not report['all_supplied_provenance_claims_consistent']:
        return False
    nonce = _json_object(provenance, MAX_PROVENANCE_BYTES)['session_nonce']
    timestamp = _now(now)
    before_digest, after_digest = _sha(before), _sha(after)
    if before_digest == after_digest:
        raise ValueError('identical capture stream digests')
    with closing(_connect(db_path)) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            _ready(con, latest)
            challenge = con.execute(
                'SELECT issued_at, expires_at, consumed FROM challenges'
                ' WHERE nonce=?', (nonce,)).fetchone()
            valid = (
                challenge is not None and not challenge[2]
                and challenge[0] <= timestamp < challenge[1]
                and con.execute(
                    'SELECT 1 FROM accepted_streams WHERE sha256 IN (?,?) LIMIT 1',
                    (before_digest, after_digest)).fetchone() is None
                and con.execute(
                    'SELECT 1 FROM accepted WHERE provenance_sha256=? LIMIT 1',
                    (_sha(provenance),)).fetchone() is None)
            con.commit()
            return bool(valid)
        except Exception:
            con.rollback()
            raise


def accept_reserved(db_path, transport, public_key, pinned_sha256,
                    *evidence, tag, now=None):
    """Fail closed before reservation; preserve intent on network failure."""
    digest = evidence_digest(evidence)
    current = _remote_head(transport, public_key, pinned_sha256, tag=tag)
    if not eligible(db_path, current, evidence, now=now):
        return False
    token = _prepare(
        db_path, current, purpose='accept', evidence_sha256=digest)
    reserved = _remote_head(
        transport, public_key, pinned_sha256, tag=tag, action='reserve',
        expected_sequence=current[0], expected_receipt_sha256=current[3],
        reservation_token=token)
    if (reserved[0] != current[0] or reserved[3] != current[3]
            or reserved[1] != current[1]):
        raise AnchorConflict('reserved custody head changed unexpectedly')
    return accept_with_latest(db_path, current, *evidence, now=now)
