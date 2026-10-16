"""Summarize GPR dependencies across a concrete MIPS caller-to-callee boundary.

The only output is register indexes and boolean boundary status. It does not
recover argument *values*, original code bytes, or unexecuted paths.
"""
import struct
try:
    from .mips_entry_dependencies import accesses, read_before_write
except ImportError:
    from mips_entry_dependencies import accesses, read_before_write


def _word(image, base, pc):
    offset = pc - base
    if offset < 0 or offset % 4 or offset + 4 > len(image):
        raise ValueError('executed PC outside supplied code image')
    return struct.unpack_from('<I', image, offset)[0]


def available_after_path(image, base, pcs):
    """Return (ready_gprs, pending_load_gpr) after an executed caller prefix.

    An immediately preceding load has not yet written back at the boundary.
    An instruction overwriting the pending destination cancels that load.
    """
    ready = {0}
    pending = None
    for pc in pcs:
        _, write, load = accesses(_word(image, base, pc))
        if pending and pending != write and pending != load:
            ready.add(pending)
        if write:
            ready.add(write)
        pending = load if load else None
    return ready, pending


def analyze_boundary(image, base, visited_pcs, entry_pc):
    """Compare callee's path-local read-before-write GPRs with caller writes.

    Caller includes its JAL and delay slot. The callee starts at the first
    executed entry_pc. It is *not* safe to infer equivalence to gameplay.
    """
    visited = tuple(visited_pcs)
    if entry_pc not in visited:
        return {'builder_entry_reached': False,
                'builder_read_before_write_gprs': [],
                'builder_inputs_prepared_by_caller': [],
                'builder_inputs_unresolved': [],
                'pending_load_at_entry_gpr': None}
    position = visited.index(entry_pc)
    caller = visited[:position]
    builder = visited[position:]
    available, pending = available_after_path(image, base, caller)
    needs = set(read_before_write(image, base, builder))
    return {
        'builder_entry_reached': True,
        'builder_read_before_write_gprs': sorted(needs),
        'builder_inputs_prepared_by_caller': sorted(needs & available),
        'builder_inputs_unresolved': sorted(needs - available),
        'pending_load_at_entry_gpr': pending,
    }
