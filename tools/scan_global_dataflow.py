#!/usr/bin/env python3
"""Conservative read-only MIPS global-reference scan, straight-line LUI windows."""
import argparse
import json
from pathlib import Path
from tools.find_global_refs import read_exe

LOADS = {32, 33, 34, 35, 36, 37, 38}
STORES = {40, 41, 42, 43, 46}

def signed16(n):
    return n - 65536 if n & 0x8000 else n

def reg_written(w):
    op = w >> 26
    if op == 0:
        fn = w & 63
        if fn == 8: return None
        if fn == 9: return (w >> 11) & 31
        if fn in (0, 2, 3, 4, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39, 42, 43):
            return (w >> 11) & 31
        return None
    if op in (1, 2, 3, 4, 5, 6, 7) or op in STORES: return None
    if op in (8, 9, 10, 11, 12, 13, 14, 15) or op in LOADS:
        return (w >> 16) & 31
    return None

def is_control(w):
    op = w >> 26
    return op in (1, 2, 3, 4, 5, 6, 7) or (op == 0 and (w & 63) in (8, 9))

def scan(code, base, target=0x800d2c3c, horizon=16):
    if len(code) % 4 or not 1 <= horizon <= 64:
        raise ValueError('invalid scan parameters')
    words = [int.from_bytes(code[i:i+4], 'little') for i in range(0, len(code), 4)]
    events = {}
    for i, instruction in enumerate(words):
        if instruction >> 26 != 15: continue
        rt = (instruction >> 16) & 31
        if not rt: continue
        known = {rt: (instruction & 0xffff) << 16}
        for j in range(i+1, min(len(words), i+horizon+1)):
            w = words[j]
            if is_control(w): break
            op = w >> 26
            rs, dest = (w >> 21) & 31, (w >> 16) & 31
            old = dict(known)
            if op in LOADS | STORES and rs in old:
                address = (old[rs] + signed16(w & 0xffff)) & 0xffffffff
                if address == target:
                    key = (base + j*4, 'store' if op in STORES else 'load')
                    distance = j-i
                    prev = events.get(key)
                    if prev is None or distance < prev['instructions_from_lui']:
                        events[key] = {'pc': f'0x{base+j*4:08x}', 'kind': key[1],
                                       'opcode': op, 'lui_pc': f'0x{base+i*4:08x}',
                                       'instructions_from_lui': distance}
            written = reg_written(w)
            if written is not None and written: known.pop(written, None)
            if op == 15 and dest:
                known[dest] = (w & 0xffff) << 16
            elif op in (8, 9) and dest and rs in old:
                known[dest] = (old[rs] + signed16(w & 0xffff)) & 0xffffffff
            elif op == 13 and dest and rs in old:
                known[dest] = old[rs] | (w & 0xffff)
            elif op == 0 and written:
                fn, a, b = w & 63, (w >> 21) & 31, (w >> 16) & 31
                if fn in (32, 33) and a in old and b in old:
                    known[written] = (old[a]+old[b]) & 0xffffffff
                elif fn in (0, 2) and b in old:
                    sh = (w >> 6) & 31
                    known[written] = ((old[b] << sh) if fn == 0 else (old[b] >> sh)) & 0xffffffff
    return sorted(events.values(), key=lambda event: (event['pc'], event['kind']))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('disc')
    p.add_argument('inventory', help='JSON from inspect_disc.py --json')
    p.add_argument('--address', type=lambda s: int(s, 0), default=0x800d2c3c)
    p.add_argument('--horizon', type=int, default=16)
    args = p.parse_args()
    entries = json.loads(Path(args.inventory).read_text(encoding='utf-8'))['entries']
    entry = next(e for e in entries if e['path'] == '/EXE/WILDARMS.EXE;1')
    base, code = read_exe(args.disc, entry)
    events = scan(code, base, args.address, args.horizon)
    print(json.dumps({'target': f'0x{args.address:08x}', 'horizon': args.horizon,
                      'loads': sum(e['kind']=='load' for e in events),
                      'stores': sum(e['kind']=='store' for e in events),
                      'events': events}, indent=2))

if __name__ == '__main__':
    main()
