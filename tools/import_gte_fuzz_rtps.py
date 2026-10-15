#!/usr/bin/env python3
"""Convert complete gte-fuzz RTPS register captures into comparison JSONL.
The supplied origin label does not authenticate the source.
"""
import argparse
import json
import re
from pathlib import Path

try:
    from .compare_gte_rtps_vectors import validate
except ImportError:
    from compare_gte_rtps_vectors import validate

REG = re.compile(r'^([><]) r\[(\d{1,2})\] = 0x([0-9a-fA-F]{8})$')
CMD = re.compile(r'^GTE 0x([0-9a-fA-F]{2}) (\w+) \(sf=([01]), lm=([01]), tx=(\d+), vx=(\d+), mx=(\d+)\)$')

def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits - 1)) else value

def lo(word):
    return signed(word, 16)

def hi(word):
    return signed(word >> 16, 16)

def unpack(before, after, sf, lm, name, source):
    # Control registers 0..31 are numbered 32..63 by GTE_READ/GTE_WRITE.
    rotation = [lo(before[32]), hi(before[32]), lo(before[33]),
                hi(before[33]), lo(before[34]), hi(before[34]),
                lo(before[35]), hi(before[35]), lo(before[36])]
    vertex = [lo(before[0]), hi(before[0]), lo(before[1])]
    inputs = (rotation + [signed(before[i], 32) for i in (37,38,39)]
              + vertex + [before[58] & 0xffff, signed(before[56],32),
                          signed(before[57],32), lo(before[59]),
                          signed(before[60],32), sf, lm])
    expected = {
        'sxy2': after[14], 'sz3': after[19] & 0xffff,
        'ir0': after[8] & 0xffff, 'ir1': lo(after[9]),
        'ir2': lo(after[10]), 'ir3': lo(after[11]),
        'mac0': signed(after[24],32), 'mac1': signed(after[25],32),
        'mac2': signed(after[26],32), 'mac3': signed(after[27],32),
        'flag': after[63],
    }
    vector = {'name':name, 'source':source,'input':inputs,'expected':expected}
    validate(vector)
    return vector

def parse_capture(text, source):
    if source not in ('hardware','external_emulator'):
        raise ValueError('source must be hardware or external_emulator')
    vectors = []
    before, after, cmd, name = {}, {}, None, None
    for lineno, raw in enumerate(text.splitlines(),1):
        line = raw.strip()
        if line.startswith('Test '):
            if cmd is not None or before or after:
                raise ValueError(f'line {lineno}: incomplete previous block')
            name = line
            continue
        match = REG.fullmatch(line)
        if match:
            direction,index,value = match.groups()
            index = int(index)
            if index >= 64:
                raise ValueError(f'line {lineno}: register index >= 64')
            if direction == '>' and cmd is not None:
                raise ValueError(f'line {lineno}: input register after command')
            target = before if direction == '>' else after
            if index in target:
                raise ValueError(f'line {lineno}: duplicate register {direction}{index}')
            if direction == '<' and cmd is None:
                raise ValueError(f'line {lineno}: output before command')
            target[index] = int(value,16)
            if len(after) == 64:
                if len(before) != 64:
                    raise ValueError(f'line {lineno}: incomplete input registers')
                opcode,label,sf,lm = cmd
                if opcode == 1 and label == 'RTPS':
                    vectors.append(unpack(before,after,sf,lm,name or f'line {lineno}',source))
                before,after,cmd,name = {},{},None,None
            continue
        match = CMD.fullmatch(line)
        if match:
            if cmd is not None or after or len(before) != 64:
                raise ValueError(f'line {lineno}: command without 64 input registers')
            opcode,label,sf,lm,tx,vx,mx = match.groups()
            if any(int(selector) > 3 for selector in (tx,vx,mx)):
                raise ValueError(f'line {lineno}: invalid command vector selection')
            if (int(opcode,16) == 1) != (label == 'RTPS'):
                raise ValueError(f'line {lineno}: inconsistent RTPS opcode/name')
            cmd = int(opcode,16),label,int(sf),int(lm)
            continue
        if line.startswith(('> r[','< r[','GTE 0x')):
            raise ValueError(f'line {lineno}: malformed register or opcode')
        if line and (before or after or cmd is not None):
            raise ValueError(f'line {lineno}: unexpected text inside register block')
    if cmd is not None or before or after:
        raise ValueError('truncated final register block')
    if not vectors:
        raise ValueError('no complete RTPS captures to import')
    return vectors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--source',choices=('hardware','external_emulator'),required=True,
                        help='Provenance must be independently verified')
    args = parser.parse_args()
    try:
        vectors = parse_capture(args.capture.read_text(encoding='utf8'),args.source)
    except ValueError as error:
        parser.error(str(error))
    args.output.write_text(''.join(json.dumps(v,sort_keys=True)+'\n' for v in vectors),
                           encoding='utf8')
    print(f'Converted {len(vectors)} RTPS captures (provenance not authenticated)')

if __name__ == '__main__':
    main()
