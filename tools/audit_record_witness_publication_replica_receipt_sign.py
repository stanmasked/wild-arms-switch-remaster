"""Reference operator-side CLI: inspect and sign ONE local archive copy.

No network transfer and no remotely trusted signing infrastructure.
The receipt is a signed observation, not a physical custody certificate.
"""
import argparse
import json
from pathlib import Path

try:
    from . import audit_record_witness_publication_replica_receipts as receipts
    from . import audit_record_witness_publication_checkpoint_cas as cas
except ImportError:
    import audit_record_witness_publication_replica_receipts as receipts
    import audit_record_witness_publication_checkpoint_cas as cas


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--role',choices=('operator-a','operator-b'),required=True)
    p.add_argument('--operator-id',required=True)
    p.add_argument('--storage-id',required=True)
    p.add_argument('--scope',required=True)
    p.add_argument('--audit-id',required=True)
    p.add_argument('--challenge',required=True)
    p.add_argument('--receipt-sequence',type=int,required=True)
    p.add_argument('--previous-receipt-sha256',required=True)
    p.add_argument('--archive-sha256',required=True)
    p.add_argument('--evidence-sha256',required=True)
    for label in ('a','b'):
        p.add_argument('--evidence-operator-'+label+'-public',
                       type=Path,required=True)
        p.add_argument('--evidence-operator-'+label+'-pin',required=True)
    p.add_argument('--signing-private',type=Path,required=True)
    p.add_argument('--signing-public',type=Path,required=True)
    p.add_argument('--signing-public-pin',required=True)
    a=p.parse_args(argv)
    result={'schema':receipts.REPORT_SCHEMA,
            'witness_fence_retirement_authorized':False,
            'witness_fence_retired':False,
            'automatic_cas_retry_authorized':False}
    try:
        result.update(receipts.attest(
            a.archive,role=a.role,
            operator_id=a.operator_id,storage_id=a.storage_id,
            scope=a.scope,audit_id=a.audit_id,nonce=a.challenge,
            receipt_sequence=a.receipt_sequence,
            previous_receipt_sha256=a.previous_receipt_sha256,
            independent_archive_pin=a.archive_sha256,
            independent_evidence_pin=a.evidence_sha256,
            evidence_operator_a_public=a.evidence_operator_a_public,
            evidence_operator_a_pin=a.evidence_operator_a_pin,
            evidence_operator_b_public=a.evidence_operator_b_public,
            evidence_operator_b_pin=a.evidence_operator_b_pin,
            receipt_signing_private=a.signing_private,
            receipt_public=a.signing_public,
            receipt_public_pin=a.signing_public_pin,
            output=a.output))
        status=0
    except (receipts.ReceiptConflict,cas.CheckpointCASConflict,ValueError,
            OSError,TypeError,KeyError,IndexError):
        result['receipt_conflict']=True
        status=1
    print(json.dumps(result,sort_keys=True))
    return status


if __name__=='__main__':
    raise SystemExit(main())
