#!/usr/bin/env python3
"""Inspect ps1-tests GTE logs without treating a pass/fail summary as RTPS data."""
import argparse
import json
import re
from pathlib import Path

PASSED = re.compile(r'^Passed tests:\s*(\d+)\s*$', re.MULTILINE)
FAILED = re.compile(r'^Failed tests:\s*(\d+)\s*$', re.MULTILINE)
REGISTER = re.compile(r'^\s*>\s*r\[(\d+)\]\s*=\s*0x([0-9a-fA-F]{1,8})\s*$', re.MULTILINE)

def inspect(text):
    passed = PASSED.findall(text)
    failed = FAILED.findall(text)
    registers = REGISTER.findall(text)
    if len(passed) == 1 and len(failed) == 1 and not registers:
        return {'kind': 'summary_only', 'passed': int(passed[0]),
                'failed': int(failed[0]), 'rtps_vectors': 0,
                'importable': False,
                'reason': 'No per-case GTE opcode, 64 input registers or expected output registers'}
    if registers:
        return {'kind': 'partial_register_log', 'register_lines': len(registers),
                'rtps_vectors': 0, 'importable': False,
                'reason': 'Register lines alone do not establish a complete RTPS input/output capture'}
    return {'kind': 'unrecognized', 'rtps_vectors': 0, 'importable': False,
            'reason': 'Not a recognized ps1-tests GTE log summary or register-line dump'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    report = inspect(args.log.read_text(encoding='utf-8'))
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 2  # Cannot emit compatible hardware snapshots from these formats.

if __name__ == '__main__':
    raise SystemExit(main())
