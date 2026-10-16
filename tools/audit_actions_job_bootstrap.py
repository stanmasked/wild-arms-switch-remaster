"""Classify GitHub Actions job *metadata*, without printing private job details.

Does not prove root cause or that project tests have passed. Never consumes
logs: a failed job with zero steps and no runner is a bootstrap symptom only.
"""
import argparse
import json
from pathlib import Path
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_JOBS = 1000


def classify(payload):
    if (not isinstance(payload, dict) or
            type(payload.get('total_count')) is not int or
            not isinstance(payload.get('jobs'), list) or
            not 0 <= payload['total_count'] or
            len(payload['jobs']) > MAX_JOBS or
            len(payload['jobs']) > payload['total_count']):
        raise ValueError('invalid Actions jobs response')
    failed = 0
    before_runner = 0
    after_steps = 0
    unresolved = 0
    for job in payload['jobs']:
        if not isinstance(job, dict):
            raise ValueError('invalid Actions job record')
        if job.get('conclusion') != 'failure':
            continue
        failed += 1
        steps = job.get('steps')
        runner = job.get('runner_name')
        if steps == [] and runner == '':
            before_runner += 1
        elif isinstance(steps, list) and len(steps) > 0:
            after_steps += 1
        else:
            unresolved += 1
    return {
        'schema': 'wild-arms-actions-bootstrap-audit-v1',
        'reported_total_jobs': payload['total_count'],
        'returned_jobs': len(payload['jobs']),
        'failed_jobs': failed,
        'failed_without_runner_or_steps': before_runner,
        'failed_with_recorded_steps': after_steps,
        'failed_without_sufficient_evidence': unresolved,
        'partial_job_page': len(payload['jobs']) < payload['total_count'],
        'all_returned_failures_pre_runner': bool(failed and before_runner == failed),
        'test_failure_proven': False,
        'infrastructure_root_cause_proven': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Privacy-safe Actions bootstrap audit')
    parser.add_argument('--jobs-json', required=True,
                        help='Path to REST /actions/runs/{id}/jobs response or - for stdin')
    args = parser.parse_args(argv)
    try:
        if args.jobs_json == '-':
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with Path(args.jobs_json).open('rb') as fd:
                data = fd.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Actions metadata exceeds bounded input size')
        report = classify(json.loads(data))
    except (ValueError, OSError, UnicodeError, TypeError):
        # No raw input, filesystem path, exception message, or job details.
        print(json.dumps({'error': 'invalid or unreadable Actions jobs metadata'}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
