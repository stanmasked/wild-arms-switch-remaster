#!/usr/bin/env python3
"""Compare external PS1 GTE RTPS snapshots with host outputs.

The 'source' field records claimed provenance; it is not authentication.
"""
import argparse
import json
import subprocess
from pathlib import Path

FIELDS = ('sxy2', 'sz3', 'ir0', 'ir1', 'ir2', 'ir3',
          'mac0', 'mac1', 'mac2', 'mac3', 'flag')
SIGNED16 = set(range(9)) | {12, 13, 14, 18}
SIGNED32 = {9, 10, 11, 16, 17, 19}
UNSIGNED16 = {15}
BOOLEANS = {20, 21}
OUTPUT_UNSIGNED32 = {'sxy2', 'flag'}
OUTPUT_UNSIGNED16 = {'sz3', 'ir0'}
OUTPUT_SIGNED16 = {'ir1', 'ir2', 'ir3'}
OUTPUT_SIGNED32 = {'mac0', 'mac1', 'mac2', 'mac3'}

def valid_int(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum

def validate(vector):
    if not isinstance(vector, dict):
        raise ValueError('vector must be an object')
    if vector.get('source') not in ('hardware', 'external_emulator'):
        raise ValueError('source must identify external hardware or emulator')
    inputs = vector.get('input')
    if not isinstance(inputs, list) or len(inputs) != 22:
        raise ValueError('expected exactly 22 integer inputs')
    for i, value in enumerate(inputs):
        if i in SIGNED16:
            bounds = (-32768, 32767)
        elif i in SIGNED32:
            bounds = (-2147483648, 2147483647)
        elif i in UNSIGNED16:
            bounds = (0, 65535)
        else:
            bounds = (0, 1)
        if not valid_int(value, *bounds):
            raise ValueError(f'input[{i}] outside allowed register range {bounds}')
    expected = vector.get('expected')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('expected must contain register values')
    for name, value in expected.items():
        if name not in FIELDS:
            raise ValueError(f'unknown output register {name}')
        if name in OUTPUT_UNSIGNED32:
            bounds = (0, 0xffffffff)
        elif name in OUTPUT_UNSIGNED16:
            bounds = (0, 65535 if name == 'sz3' else 4096)
        elif name in OUTPUT_SIGNED16:
            bounds = (-32768, 32767)
        else:
            bounds = (-2147483648, 2147483647)
        if not valid_int(value, *bounds):
            raise ValueError(f'{name} outside allowed register range {bounds}')
    return expected

def compare(vector, output):
    expected = validate(vector)
    for key in expected:
        if key not in output:
            raise ValueError(f'runner missing output {key}')
    return {key: {'expected': value, 'actual': output[key]}
            for key, value in expected.items() if output[key] != value}

def run_case(binary, vector):
    validate(vector)
    line = ' '.join(map(str, vector['input'])) + '\n'
    done = subprocess.run([str(binary)], input=line, text=True, capture_output=True,
                          check=True, timeout=10)
    values = list(map(int, done.stdout.strip().split()))
    if len(values) != len(FIELDS):
        raise RuntimeError('host runner output has invalid field count')
    return dict(zip(FIELDS, values))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('runner', type=Path)
    parser.add_argument('vectors', type=Path)
    args = parser.parse_args()
    total = mismatches = 0
    for number, line in enumerate(args.vectors.read_text(encoding='utf8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            vector = json.loads(line)
            delta = compare(vector, run_case(args.runner, vector))
        except (ValueError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            parser.error(f'line {number}: {exc}')
        total += 1
        if delta:
            mismatches += 1
            print(json.dumps({'line': number, 'name': vector.get('name', str(number)),
                              'differences': delta}, sort_keys=True))
    if not total:
        parser.error('no external vectors; a zero-vector PASS is not allowed')
    print(f'External GTE vectors: {total}; mismatched cases: {mismatches}')
    return 1 if mismatches else 0

if __name__ == '__main__':
    raise SystemExit(main())
