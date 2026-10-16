"""Classify *executed* MIPS arithmetic order leading to final matrix SH slots.

This follows symbolic operation shapes, not coefficient values. It can
recognize a signed MULT/MFLO with SRA12 before or after three ADDUs. Only
observed instruction PCs and successful memory events are considered.
Guest code, register contents, private addresses and coefficients are never
returned. Unknown instructions/data origins are not reverse-engineered.
"""
from dataclasses import dataclass
import struct

try:
    from .mips_control_flow import LOADS, STORES
except ImportError:
    from mips_control_flow import LOADS, STORES


@dataclass(frozen=True)
class Node:
    kind: str
    args: tuple = ()


ZERO = Node('zero')
INPUT = Node('input')
UNKNOWN = Node('unknown')


def _alu(word, regs, hi, lo):
    op = word >> 26
    rs, rt, rd, sa, fn = ((word >> 21) & 31, (word >> 16) & 31,
                           (word >> 11) & 31, (word >> 6) & 31, word & 63)
    a, b = regs[rs], regs[rt]
    if word == 0:
        return None, None, hi, lo
    if op == 0:
        if fn == 8:  # JR
            return None, None, hi, lo
        if fn == 9:  # JALR writes return PC, not a data operand
            return rd, Node('link'), hi, lo
        if fn in (24, 25):
            product = Node('mult' if fn == 24 else 'multu', (a, b))
            return None, None, product, product
        if fn in (16, 18):
            origin = hi if fn == 16 else lo
            return rd, Node('mfhi' if fn == 16 else 'mflo', (origin,)), hi, lo
        if fn in (17, 19):
            return (None, None, a if fn == 17 else hi,
                    a if fn == 19 else lo)
        if fn == 3 and sa == 12 and rs == 0:
            return rd, Node('sra12', (b,)), hi, lo
        if fn == 33 and sa == 0:  # ADDU: wraps without trapping on overflow
            if a == ZERO:
                return rd, b, hi, lo
            if b == ZERO:
                return rd, a, hi, lo
            return rd, Node('add', (a, b)), hi, lo
        if fn in (0, 2, 3, 4, 6, 7, 32, 34, 35, 36, 37, 38, 39, 42, 43):
            return rd, Node('other', (a, b)), hi, lo
        return None, None, hi, lo
    if op == 3:
        return 31, Node('link'), hi, lo
    if op in (8, 9):
        immediate = word & 65535
        if immediate == 0:
            return rt, a, hi, lo
        if rs == 0 and immediate == 0:
            return rt, ZERO, hi, lo
        if rs == 0:
            return rt, Node('constant'), hi, lo
        return rt, Node('other', (a,)), hi, lo
    if op in (10, 11, 12, 13, 14, 15):
        return rt, Node('constant' if op == 15 else 'other', (a,)), hi, lo
    if op in (1, 2, 4, 5, 6, 7, 20, 21, 22, 23):
        return None, None, hi, lo
    return None, None, hi, lo


def _terms(expr, max_nodes=512):
    """Flatten ADDU trees and omit accumulator initialization to zero."""
    terms = []
    stack = [expr]
    traversed = 0
    while stack:
        traversed += 1
        if traversed > max_nodes:
            return None
        item = stack.pop()
        if item.kind == 'add':
            stack.extend(reversed(item.args))
        elif item.kind != 'zero':
            terms.append(item)
    return terms


def _is_signed_product(expr):
    return (expr.kind == 'mflo' and len(expr.args) == 1
            and expr.args[0].kind == 'mult')


def classify(expr):
    """Return recognized exact structural schedule, otherwise unclassified."""
    if expr is None:
        return 'not_written', 0
    if expr.kind == 'sra12':
        terms = _terms(expr.args[0])
        if terms is not None and len(terms) == 3 and all(map(_is_signed_product, terms)):
            return 'shift_after_three_products', 3
        if _is_signed_product(expr.args[0]):
            return 'single_product_sra12', 1
    terms = _terms(expr)
    if (terms is not None and len(terms) == 3
            and all(t.kind == 'sra12' and len(t.args) == 1 and
                    _is_signed_product(t.args[0]) for t in terms)):
        return 'shift_each_of_three_products', 3
    return 'unclassified', 0


def summarize(image, base, trace, matrix_address, *, matrix_slots=9):
    """Classify final successful SH results with exact byte-overwrite handling.

    A partial or failed guest run may classify already-written slots, but the
    output retains the incomplete-execution warning. No real game schedule is
    presumed before a private original-executable probe has actually run.
    """
    if (not isinstance(base, int) or base & 3 or len(image) & 3 or
            not isinstance(matrix_address, int) or matrix_address & 1 or
            not isinstance(matrix_slots, int) or not 1 <= matrix_slots <= 128):
        raise ValueError('invalid image or matrix configuration')
    regs = [INPUT] * 32
    regs[0] = ZERO
    hi = lo = UNKNOWN
    pending = None
    load_events = iter(trace['load_accesses'])
    store_events = iter(trace['store_addresses'])
    mem = {}  # private byte-addressed symbolic memory shadow
    slots = [None] * matrix_slots
    for pc in trace['visited_pcs']:
        if (not isinstance(pc, int) or pc < base or
                (pc-base) % 4 or pc + 4 > base+len(image)):
            raise ValueError('executed PC outside supplied image')
        word, = struct.unpack_from('<I', image, pc-base)
        op, rt = word >> 26, (word >> 16) & 31
        dst, value, next_pending = None, None, None
        if op in LOADS:
            event = next(load_events, None)
            if (event is None or len(event) != 4 or event[0] != pc or
                    event[2] != LOADS[op] or event[3] != rt):
                raise ValueError('mismatched successful MIPS load event')
            address, width = event[1], event[2]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('invalid successful load address')
            origins = [mem.get(address+i) for i in range(width)]
            origin = (origins[0] if origins[0] is not None and
                      all(o == origins[0] for o in origins) else Node('load'))
            next_pending = (rt, origin) if rt else None
        elif op in STORES:
            address = next(store_events, None)
            width = STORES[op]
            if not isinstance(address, int) or address < 0 or address % width:
                raise ValueError('missing or invalid successful store address')
            written = regs[rt]  # before the preceding LW retires
            for i in range(width):
                mem[address+i] = written
            for index in range(matrix_slots):
                slot = matrix_address + 2*index
                if address < slot+2 and address+width > slot:
                    slots[index] = written if op == 41 and address == slot else None
        else:
            dst, value, hi, lo = _alu(word, regs, hi, lo)
        if pending is not None and pending[0] != dst and (
                next_pending is None or pending[0] != next_pending[0]):
            regs[pending[0]] = pending[1]
        if dst:
            regs[dst] = value
        regs[0] = ZERO
        pending = next_pending
    if next(load_events, None) is not None or next(store_events, None) is not None:
        raise ValueError('unconsumed MIPS load/store event')
    categories = ('single_product_sra12', 'shift_after_three_products',
                  'shift_each_of_three_products', 'unclassified', 'not_written')
    counted = {category: 0 for category in categories}
    slot_report = []
    for index, expr in enumerate(slots):
        kind, products = classify(expr)
        counted[kind] += 1
        slot_report.append({'slot_index': index, 'schedule': kind,
                            'proven_signed_product_terms': products})
    return {
        'arithmetic_schedule_counts': counted,
        'matrix_slots': slot_report,
        'slots_with_recognized_schedule': sum(counted[c] for c in categories[:3]),
        'guest_execution_completed': bool(trace['completed']),
        'synthetic_inputs_only': True,
        'original_builder_schedule_identified': False,
        'bit_exact_ps1_equivalence_proven': False,
        'private_values_emitted': False,
    }
