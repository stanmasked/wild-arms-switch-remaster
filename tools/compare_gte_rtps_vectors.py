#!/usr/bin/env python3
"""Compare captured PlayStation GTE RTPS snapshots against the C++ host model.

JSONL: {"source":"hardware"|"external_emulator","input":[22 ints],
        "expected":{"sxy2":integer,...},"name":"optional"}
Source values are provenance labels, not proof of the capture's authenticity.
"""
import argparse
import json
import subprocess
from pathlib import Path

FIELDS = ('sxy2', 'sz3', 'ir0', 'ir1', 'ir2', 'ir3',
          'mac0', 'mac1', 'mac2', 'mac3', 'flag')

def compare(vector, output):
    if vector.get('source') not in ('hardware', 'external_emulator'):
        raise ValueError('source must identify external hardware or emulator')
    if len(vector['input']) != 22 or not all(isinstance(x, int) and not isinstance(x, bool) for x in vector['input']):
        raise ValueError('expected exactly 22 integer inputs')
    expected = vector['expected']
    if not expected or any(k not in FIELDS or not isinstance(v, int) for k,v in expected.items()):
        raise ValueError('expected must contain numeric GTE register results')
    return {key: {'expected':value,'actual':output[key]} for key,value in expected.items()
            if output[key] != value}

def run_case(binary, vector):
    line = ' '.join(map(str, vector['input'])) + '\n'
    done = subprocess.run([str(binary)],input=line,text=True,capture_output=True,check=True)
    values = list(map(int,done.stdout.strip().split()))
    if len(values) != len(FIELDS):
        raise RuntimeError('host runner output has invalid field count')
    return dict(zip(FIELDS,values))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('runner',type=Path)
    ap.add_argument('vectors',type=Path)
    args = ap.parse_args()
    total = 0
    mismatches = 0
    for number,line in enumerate(args.vectors.read_text(encoding='utf8').splitlines(),1):
        if not line.strip():
            continue
        vector = json.loads(line)
        delta = compare(vector,run_case(args.runner,vector))
        total += 1
        if delta:
            mismatches += 1
            print(json.dumps({'line':number,
                              'name':vector.get('name',str(number)),
                              'differences':delta},sort_keys=True))
    if not total:
        ap.error('no external vectors; a zero-vector PASS is not allowed')
    print(f'External GTE vectors: {total}; mismatched cases: {mismatches}')
    return 1 if mismatches else 0

if __name__ == '__main__':
    raise SystemExit(main())
